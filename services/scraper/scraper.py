# --------------------------------------------------------------
# scraper.py – full, corrected import section
# --------------------------------------------------------------

# ---------- Standard library ----------
import asyncio
import base64
import re
import time
from datetime import timedelta
from functools import wraps
from typing import Any, Dict, List, Optional, Set, TYPE_CHECKING
from queue import Queue

# ----------------------------------------------------------------------
# Conditional alias for the Playwright Page class (used only in type hints)
# ----------------------------------------------------------------------
# ``PlaywrightPage`` is referenced in the ``BrowserContext`` constructor
# When static type checking runs (IDE, mypy, Pylance) we import the real
# class so the checker knows the exact type.  At runtime we fall back to
# ``Any`` – the code works even if Playwright isn’t installed.
if TYPE_CHECKING:                     # pragma: no cover
    from playwright.async_api import Page as PlaywrightPage
else:
    PlaywrightPage = Any  # type: ignore

# Import the *module* name so forward‑reference strings like
# "playwright.async_api.Page" don’t raise “undefined variable” warnings.
# This import is deliberately guarded – it won’t crash if Playwright isn’t present.
try:
    import playwright  # noqa: F401  (imported for type‑checking only)
except Exception:  # pragma: no cover
    playwright = None  # type: ignore

# ---------- Selenium / WebDriver ----------
from selenium import webdriver
from selenium.common.exceptions import (
    WebDriverException,
    TimeoutException,
    StaleElementReferenceException,
)
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

# ---------- HTML / parsing ----------
from bs4 import BeautifulSoup
import html2text

# ---------- Logging ----------
from loguru import logger

# ---------- Third‑party helpers ----------
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# ---------- Project‑specific imports ----------
from core.config import get_settings

# Cache layer
from services.cache.cache_service import CacheService

# Extraction utilities
from services.extractors.structured_data import StructuredDataExtractor

# Config loader – already works
from services.crawler.config_loader import get_campaign_config

# Metrics for monitoring
from prometheus_client import Counter, Histogram, Gauge

# Max Browsers
MAX_BROWSERS = 5

# ----------------------------------------------------------------------
# Compatibility shim – makes a Playwright browser look like the small
# subset of Selenium that the rest of the code expects.
# ----------------------------------------------------------------------
class SeleniumLikeBrowser:
    """
    Thin wrapper exposing the three Selenium‑style members used by the
    scraper pool: ``set_page_load_timeout``, ``title`` and ``quit``.
    All other attributes are delegated to the underlying Playwright
    objects (browser, context, page) so they can still be accessed if
    needed.
    """
    def __init__(self, browser: Any, context: Any, page: Any):
        self._browser = browser      # Playwright Browser
        self._context = context      # Playwright BrowserContext
        self._page = page            # Playwright Page

    # ----- Selenium‑style API -------------------------------------------------
    def set_page_load_timeout(self, seconds: int) -> None:  # pragma: no cover
        """Playwright uses milliseconds for navigation timeouts."""
        timeout_ms = seconds * 1000
        try:
            # Newer Playwright versions
            self._context.set_default_navigation_timeout(timeout_ms)
        except Exception:
            # Fallback for older releases
            self._context.set_default_timeout(timeout_ms)

    @property
    def title(self) -> str:  # pragma: no cover
        """Return the current page title."""
        try:
            return self._page.title()
        except Exception:
            return ""

    def quit(self) -> None:  # pragma: no cover
        """Close the underlying Playwright browser."""
        try:
            self._browser.close()
        except Exception:
            pass

    # ----- Delegation helpers -------------------------------------------------
    def __getattr__(self, name: str) -> Any:
        """
        Forward any unknown attribute to the underlying Playwright objects.
        This keeps the wrapper flexible without having to expose every method manually.
        """
        for obj in (self._browser, self._context, self._page):
            if hasattr(obj, name):
                return getattr(obj, name)
        raise AttributeError(name)

SCRAPE_REQUESTS = Counter('scraper_requests_total', 'Total number of scrape requests')
SCRAPE_ERRORS = Counter('scraper_errors_total', 'Total number of scrape errors')
SCRAPE_DURATION = Histogram('scraper_duration_seconds', 'Time spent scraping URLs')

# Browser Pool Metrics
BROWSER_POOL_SIZE = Gauge('browser_pool_size', 'Current number of browsers in pool')
BROWSER_CREATION_TOTAL = Counter('browser_creation_total', 'Total number of browsers created')
BROWSER_REUSE_TOTAL = Counter('browser_reuse_total', 'Total number of times browsers were reused')
BROWSER_FAILURES = Counter('browser_failures_total', 'Total number of browser creation/initialization failures')
BROWSER_CLEANUP_TOTAL = Counter('browser_cleanup_total', 'Total number of browser cleanup operations')

# Browser Health Metrics
BROWSER_MEMORY_USAGE = Histogram(
    'browser_memory_usage_bytes',
    'Browser memory usage in bytes',
    buckets=[
        100 * 1024 * 1024,      # 100 MiB
        500 * 1024 * 1024,      # 500 MiB
        1024 * 1024 * 1024,     # 1 GiB
    ],
)
BROWSER_HEALTH_CHECK_DURATION = Histogram(
    'browser_health_check_seconds',
    'Time spent on browser health checks',
)

# Navigation Metrics
PAGE_LOAD_DURATION = Histogram('page_load_duration_seconds', 'Time taken for page loads')
NETWORK_IDLE_WAIT_DURATION = Histogram('network_idle_wait_seconds', 'Time spent waiting for network idle')

# Cloudflare Metrics
CLOUDFLARE_CHALLENGES = Counter('cloudflare_challenges_total', 'Number of Cloudflare challenges encountered')
CLOUDFLARE_BYPASS_SUCCESS = Counter('cloudflare_bypass_success_total', 'Successful Cloudflare challenge bypasses')
CLOUDFLARE_BYPASS_FAILURE = Counter('cloudflare_bypass_failure_total', 'Failed Cloudflare challenge bypasses')

settings = get_settings()


# ----------------------------------------------------------------------
# Helper decorators
# ----------------------------------------------------------------------
def with_retry(max_retries: int = 3, delay: float = 1.0):
    """Simple async retry decorator used by a few internal calls."""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except Exception as exc:  # pylint: disable=broad-except
                    last_exc = exc
                    logger.warning(f"Attempt {attempt + 1}/{max_retries} failed: {exc}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(delay * (attempt + 1))
            raise last_exc
        return wrapper
    return decorator


# ----------------------------------------------------------------------
# Selenium‑only safe_get_url (kept for compatibility)
# ----------------------------------------------------------------------
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    retry=retry_if_exception_type(WebDriverException)
)
def safe_get_url(browser: webdriver.Chrome, url: str, timeout: int):
    """Safely navigate to a URL with Selenium, applying a timeout."""
    browser.set_page_load_timeout(timeout)
    return browser.get(url)


# ----------------------------------------------------------------------
# Content extraction (unchanged apart from minor refactoring)
# ----------------------------------------------------------------------
class ContentExtractor:
    """Enhanced content extraction with better cleaning and extraction logic."""

    def __init__(self):
        self.html2text_handler = html2text.HTML2Text()
        self.html2text_handler.ignore_links = False
        self.html2text_handler.ignore_images = False
        self.html2text_handler.ignore_tables = False
        self.html2text_handler.body_width = 0

    def _clean_html(self, html: str) -> str:
        """Strip unwanted tags/attributes."""
        soup = BeautifulSoup(html, 'html.parser')
        for element in soup.find_all([
            'script', 'style', 'iframe', 'nav', 'footer',
            'noscript', 'meta', 'link', 'comment'
        ]):
            element.decompose()

        for tag in soup.find_all(True):
            allowed = {'href', 'src', 'alt', 'title'}
            for attr in list(tag.attrs):
                if attr not in allowed:
                    del tag[attr]

        return str(soup)

    def _extract_metadata(self, soup: BeautifulSoup) -> Dict[str, str]:
        """Pull common meta tags."""
        metadata = {}

        title_tag = soup.find('meta', property='og:title') or soup.find('title')
        if title_tag:
            metadata['title'] = title_tag.get('content', '') or title_tag.string

        mappings = {
            'description': ['description', 'og:description'],
            'language': ['language', 'og:locale'],
            'author': ['author', 'article:author'],
            'published_date': ['article:published_time', 'publishedDate'],
            'keywords': ['keywords'],
            'image': ['og:image']
        }

        for meta in soup.find_all('meta'):
            name = meta.get('name') or meta.get('property')
            content = meta.get('content')
            if name and content:
                for key, candidates in mappings.items():
                    if name.lower() in candidates:
                        metadata[key] = content.strip()
        return metadata

    def _find_main_content(self, soup: BeautifulSoup) -> Optional[str]:
        """Heuristic to locate the primary article body."""
        patterns = [
            {'tag': 'main'},
            {'tag': 'article'},
            {'tag': 'div', 'id': re.compile(r'content|main|article', re.I)},
            {'tag': 'div', 'class': re.compile(r'content|main|article', re.I)},
            {'tag': 'div', 'role': 'main'}
        ]
        for pat in patterns:
            el = soup.find(**pat)
            if el:
                return str(el)

        # Fallback: biggest text container
        containers = soup.find_all(['div', 'section'])
        if containers:
            return str(max(containers, key=lambda x: len(x.get_text())))

        return None

    async def extract_content(self, html: str, only_main: bool = True) -> Dict[str, Any]:
        """Return cleaned HTML, markdown, and metadata."""
        soup = BeautifulSoup(html, 'html.parser')
        metadata = self._extract_metadata(soup)

        if only_main:
            main = self._find_main_content(soup)
            if main:
                html = main

        clean_html = self._clean_html(html)
        markdown = self.html2text_handler.handle(clean_html)

        return {
            'html': clean_html,
            'markdown': markdown,
            'metadata': metadata
        }


# ----------------------------------------------------------------------
# Cloudflare handling (unchanged except for small logging tweaks)
# ----------------------------------------------------------------------
class CloudflareHandler:
    def __init__(self):
        self.cf_challenge_selectors = [
            "#challenge-form",
            "#challenge-running",
            "div[class*='cf-browser-verification']",
            "#cf-challenge-running"
        ]

    async def is_cloudflare_challenge(self, browser: webdriver.Chrome) -> bool:
        """Detect whether the current page is a Cloudflare interstitial."""
        try:
            title = browser.title.lower()
            if "just a moment" in title or "attention required" in title:
                logger.info("Cloudflare challenge detected via title")
                return True

            for selector in self.cf_challenge_selectors:
                try:
                    if browser.find_element(By.CSS_SELECTOR, selector):
                        logger.info(f"Cloudflare challenge element found: {selector}")
                        return True
                except Exception:
                    continue

            src = browser.page_source.lower()
            indicators = [
                "cloudflare",
                "ray id:",
                "please wait while we verify",
                "please enable cookies",
                "please complete the security check"
            ]
            if any(ind in src for ind in indicators):
                logger.info("Cloudflare challenge detected via page source")
                return True

            return False
        except Exception as exc:  # pylint: disable=broad-except
            logger.error(f"Error checking Cloudflare challenge: {exc}")
            return False

    async def solve_challenge(self, browser: webdriver.Chrome) -> bool:
        """Attempt a simple checkbox click if present."""
        try:
            # Switch to iframe if there is one
            try:
                iframe = WebDriverWait(browser, 5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "iframe[title*='challenge']"))
                )
                browser.switch_to.frame(iframe)
            except Exception:
                pass

            # Click a checkbox if we see it
            try:
                cb = WebDriverWait(browser, 5).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, "input[type='checkbox'], .checkbox"))
                )
                if cb.is_displayed():
                    cb.click()
                    logger.info("Clicked Cloudflare challenge checkbox")
            except Exception:
                pass

            browser.switch_to.default_content()
            return True
        except Exception as exc:  # pylint: disable=broad-except
            logger.error(f"Error solving Cloudflare challenge: {exc}")
            return False

    async def wait_for_challenge_completion(self, browser: webdriver.Chrome, timeout: int = 30) -> bool:
        """Poll until the challenge disappears, trying to solve it a few times."""
        start = time.time()
        attempts = 0
        while time.time() - start < timeout:
            if not await self.is_cloudflare_challenge(browser):
                logger.info("Cloudflare challenge resolved")
                return True

            if attempts < 3:
                await self.solve_challenge(browser)
                attempts += 1
                logger.info(f"Cloudflare solve attempt {attempts}")

            await asyncio.sleep(2)

        logger.warning("Cloudflare challenge timed out")
        return False


# ----------------------------------------------------------------------
# Browser – thin wrapper that presents a Selenium‑like API over Playwright
# ----------------------------------------------------------------------
class Browser:
    """
    Wrapper around Playwright's Browser, BrowserContext, and Page objects.
    Provides the small subset of Selenium‑style methods that the rest of the
    scraper pool expects (set_page_load_timeout, title, quit).
    """
    def __init__(self, browser: Any, context: Any, page: Any):
        # Playwright objects
        self.browser = browser      # Playwright Browser
        self.context = context      # Playwright BrowserContext
        self.page = page            # Playwright Page

        # ------------------------------------------------------------------
        # Compatibility shim – the rest of the code expects Selenium‑like APIs.
        # ------------------------------------------------------------------

    # Selenium‑style timeout setter → Playwright navigation timeout (ms)
    def set_page_load_timeout(self, seconds: int) -> None:  # pragma: no cover
        """Set the maximum time to wait for a page load (seconds)."""
        timeout_ms = seconds * 1000
        # Newer Playwright versions expose set_default_navigation_timeout;
        # older ones use set_default_timeout.
        try:
            self.context.set_default_navigation_timeout(timeout_ms)
        except Exception:
            self.context.set_default_timeout(timeout_ms)

    # Selenium‑style `title` property → Playwright page title
    @property
    def title(self) -> str:  # pragma: no cover
        """Return the current page title."""
        try:
            return self.page.title()
        except Exception:
            return ""

    # Selenium‑style `quit` → Playwright browser close
    def quit(self) -> None:  # pragma: no cover
        """Close the underlying Playwright browser."""
        try:
            self.browser.close()
        except Exception:
            pass


# ----------------------------------------------------------------------
# BrowserContext – wraps a Playwright page and adds helpers
# ----------------------------------------------------------------------
class BrowserContext:
    """
    Wraps a Playwright Page, providing navigation, screenshots, etc.
    """
    # NOTE: ``page`` is a Playwright ``Page`` instance.
    # We import the class only when type‑checking so the runtime does not
    # require Playwright to be present.
    def __init__(self, driver: SeleniumLikeBrowser, config: Dict[str, Any]):
        """
        ``driver`` is the Selenium‑compatible shim that wraps the real
        Playwright objects.  All existing code that expects a Selenium‑like
        ``browser`` attribute will now work because the shim provides those
        members.
        """
        # Keep a reference to the Playwright page for any direct calls
        self.page = driver._page          # type: ignore[attr-defined]
        # Expose the shim as ``self.browser`` – this is what the rest of the
        # scraper pool uses (title, set_page_load_timeout, quit, etc.).
        self.browser = driver

        self.cloudflare_handler = CloudflareHandler()

        # Hardening will be applied later – callers must await it.
        # e.g.  await ctx.apply_hardening()

    # ------------------------------------------------------------------
    # Helper used by the pool’s health‑check and destroy logic
    # ------------------------------------------------------------------
    async def close(self) -> None:
        """Close the page (and its browser if we own it)."""
        if self.page:
            await self.page.close()
        # If we created the browser ourselves, shut it down.
        if getattr(self, "browser", None):
            try:
                await self.browser.close()
            except Exception:  # pragma: no cover
                pass

    async def apply_hardening(self) -> None:
        """Apply anti‑detection tricks and performance tweaks for Playwright."""
        logger.debug("Applying browser hardening & performance settings")
        try:
            # Enforce viewport size (replaces Selenium's set_window_size)
            await self.browser._page.set_viewport_size(
                {
                    "width": self.config.get("window_width", 1280),
                    "height": self.config.get("window_height", 1024),
                }
            )
        except Exception as exc:  # pragma: no cover
            logger.warning(f"Failed to set viewport size: {exc}")

            # Set sensible timeouts (Playwright equivalents of Selenium timeouts)
            await self.browser._context.set_default_navigation_timeout(30_000)  # 30 s
            await self.browser._context.set_default_timeout(30_000)            # 30 s

            # Anti‑automation script
            await self.page.add_init_script(
                """
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
                Object.defineProperty(navigator, 'languages', {get: () => ['en-US','en']});
                window.chrome = {runtime: {}};
                """
            )

            # Spoof a realistic user‑agent
            await self.browser._context.set_user_agent(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )

            # Extra HTTP headers (helps against basic bot detection)
            await self.browser._context.set_extra_http_headers(
                {
                    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                    "accept-language": "en-US,en;q=0.9",
                    "sec-ch-ua": '"Not_A Brand";v="8", "Chromium";v="120"',
                    "sec-ch-ua-mobile": "?0",
                    "sec-ch-ua-platform": '"Windows"',
                    "sec-fetch-dest": "document",
                    "sec-fetch-mode": "navigate",
                    "sec-fetch-site": "none",
                    "sec-fetch-user": "?1",
                    "upgrade-insecure-requests": "1",
                }
            )
            logger.info("Browser hardening applied")
        except Exception as exc:  # pylint: disable=broad-except
            logger.error(f"Failed to apply browser hardening: {exc}")
            raise

    async def navigate(self, url: str, timeout: int = 30):
        """Navigate to a URL, handling Cloudflare if it appears."""
        logger.info(f"Navigating to {url}")
        start = time.time()
        try:
            self.browser.set_page_load_timeout(timeout)
            self.browser.get(url)

            if await self.cloudflare_handler.is_cloudflare_challenge(self.browser):
                CLOUDFLARE_CHALLENGES.inc()
                logger.info("Cloudflare challenge detected – waiting")
                solved = await self.cloudflare_handler.wait_for_challenge_completion(
                    self.browser, timeout=timeout
                )
                if solved:
                    CLOUDFLARE_BYPASS_SUCCESS.inc()
                else:
                    CLOUDFLARE_BYPASS_FAILURE.inc()
                    raise RuntimeError("Unable to bypass Cloudflare challenge")

            await self._wait_for_network_idle()
            logger.info(f"Navigation finished in {time.time() - start:.2f}s")
        except TimeoutException:
            logger.warning("Page load timed out – retrying with larger timeout")
            self.browser.execute_script("window.stop();")
            self.browser.set_page_load_timeout(timeout * 2)
            self.browser.get(url)
            await self._wait_for_network_idle()
        except Exception as exc:  # pylint: disable=broad-except
            logger.error(f"Navigation error: {exc}")
            raise

    async def _wait_for_network_idle(self, idle_time: float = 1.0, timeout: float = 10.0):
        """Poll the performance timeline until no new resources appear."""
        logger.debug("Waiting for network idle")
        script = """
            return new Promise(resolve => {
                let last = performance.getEntriesByType('resource').length;
                let same = 0;
                const check = () => {
                    const cur = performance.getEntriesByType('resource').length;
                    if (cur === last) {
                        same += 1;
                        if (same >= 3) resolve({resources: cur});
                    } else {
                        same = 0;
                        last = cur;
                    }
                    setTimeout(check, 300);
                };
                check();
            });
        """
        try:
            await asyncio.get_event_loop().run_in_executor(
                None, lambda: self.browser.execute_script(script)
            )
            logger.debug("Network idle detected")
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning(f"Network idle wait failed: {exc}")

    async def get_page_source(self) -> str:
        """Return the current page source, retrying on stale references."""
        for attempt in range(3):
            try:
                src = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: self.browser.page_source
                )
                return src
            except StaleElementReferenceException:
                logger.warning(f"Stale page source on attempt {attempt + 1}")
                await asyncio.sleep(0.5)
        raise RuntimeError("Unable to retrieve page source after retries")

    async def take_screenshot(self) -> Optional[str]:
        """Capture a PNG screenshot and return it base64‑encoded."""
        try:
            png = await asyncio.get_event_loop().run_in_executor(
                None, lambda: self.browser.get_screenshot_as_png()
            )
            return base64.b64encode(png).decode('utf-8')
        except Exception as exc:  # pylint: disable=broad-except
            logger.error(f"Screenshot failed: {exc}")
            return None

    async def cleanup(self):
        """Clear cookies, storage, and close the Playwright page."""
        try:
            # Remove all cookies from the page's context
            await self.browser.context.clear_cookies()

            # Clear localStorage and sessionStorage
            await self.browser.evaluate("window.localStorage.clear();")
            await self.browser.evaluate("window.sessionStorage.clear();")

            # Close the page (and its context)
            await self.browser.close()
        except Exception as exc:
            # Broad‑except is fine for a cleanup routine; we just log the issue.
            logger.warning(f"Issue during browser cleanup: {exc}")


# ----------------------------------------------------------------------
# BrowserPool – manages a bounded set of Selenium browsers
# ----------------------------------------------------------------------
class BrowserPool:
    """
    A lightweight async‑compatible pool that creates Playwright Chromium
    instances on demand, reuses them, and periodically validates health.
    """

    def __init__(self, maxsize: int = 5, config: dict | None = None):
        """
        Parameters
        ----------
        maxsize: int
            Maximum number of concurrent browsers.
        config: dict | None
            Optional dictionary of default BrowserContext options
            (e.g. window size, timeout).  It will be passed to every
            BrowserContext that the pool creates.
        """
        self._maxsize = maxsize
        self._available = Queue(maxsize)
        self._active = set()
        self._playwright = None
        self._config = config or {}

        # ---- internal bookkeeping -------------------------------------------------
        self._lock = asyncio.Lock()          # protects pool state
        self.max_browsers = maxsize           # convenience alias used in get_browser
        self._shutdown = False               # set to True during cleanup
        # -------------------------------------------------------------------------

    async def _create_browser(self) -> BrowserContext:
        """Instantiate a fresh head‑less Chromium browser using Playwright."""
        # Import lazily – the optional block above guarantees the name exists.
        from playwright.async_api import async_playwright

        logger.info("Creating new Playwright Chromium instance")

        # Start Playwright only when we actually need it.
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=True,
            args=[
                "--disable-gpu",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
            ],
        )

        # Create a browser context with the desired viewport.
        context = await self._browser.new_context(
            viewport={"width": 1280, "height": 1024},
            java_script_enabled=True,
        )
        page = await context.new_page()

        # ------------------------------------------------------------------
        # Build the Selenium‑compatible shim and hand it to BrowserContext.
        # ------------------------------------------------------------------
        shim = SeleniumLikeBrowser(
            browser=self._browser,   # the Playwright Browser we just launched
            context=context,
            page=page,
        )

        # Return the BrowserContext that now receives the shim.
        ctx = BrowserContext(driver=shim, config=self._config)

        # ----------------------- Prometheus metrics -----------------------
        BROWSER_CREATION_TOTAL.inc()
        BROWSER_POOL_SIZE.set(
            self._available.qsize() + len(self._active) + 1
        )
        # ------------------------------------------------------------------

        return ctx

    async def get_browser(self) -> BrowserContext:
        """Acquire a browser from the pool, creating one if necessary."""
        async with self._lock:
            if self._shutdown:
                raise RuntimeError("BrowserPool is shutting down")

            # Prefer an existing idle browser
            if not self._available.empty():
                ctx = await self._available.get()
                self._active.add(id(ctx))
                BROWSER_REUSE_TOTAL.inc()
                logger.debug(f"Reusing browser {id(ctx)}")
                return ctx

            # If we haven't hit the limit, spin up a new one
            if len(self._active) < self.max_browsers:
                ctx = await self._create_browser()
                self._active.add(id(ctx))
                logger.debug(f"Created browser {id(ctx)}")
                return ctx

        # Pool exhausted – wait for a free browser
        logger.info("Pool exhausted, awaiting free browser")
        ctx = await self._available.get()
        async with self._lock:
            self._active.add(id(ctx))
        return ctx

    async def release_browser(self, ctx: BrowserContext):
        """Return a browser to the pool (or discard if unhealthy)."""
        async with self._lock:
            browser_id = id(ctx)
            if browser_id not in self._active:
                logger.warning(f"Tried to release unknown browser {browser_id}")
                return

            self._active.remove(browser_id)

            # Quick health check – if the session is dead we recreate later
            try:
                ctx.browser.title  # simple ping
                await self._available.put(ctx)
                logger.debug(f"Browser {browser_id} returned to pool")
            except Exception as exc:  # pylint: disable=broad-except
                logger.error(f"Browser {browser_id} failed health check: {exc}")
                await self._destroy_browser(ctx)

            BROWSER_POOL_SIZE.set(self._available.qsize() + len(self._active))

    async def _destroy_browser(self, ctx: BrowserContext):
        """Force‑close a Selenium‑like driver."""
        try:
            await asyncio.get_event_loop().run_in_executor(None, ctx.browser.quit)
            logger.info(f"Destroyed browser {id(ctx)}")
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning(f"Error destroying browser {id(ctx)}: {exc}")

    async def cleanup(self):
        """Gracefully shut down all browsers."""
        async with self._lock:
            self._shutdown = True
            logger.info("Cleaning up BrowserPool – closing all browsers")

            # Drain the queue first
            while not self._available.empty():
                ctx = await self._available.get()
                await self._destroy_browser(ctx)

            # Log any browsers that were still marked active (should be none)
            for bid in list(self._active):
                logger.warning(f"Browser {bid} still marked active during shutdown")
            self._active.clear()

            BROWSER_POOL_SIZE.set(0)
            BROWSER_CLEANUP_TOTAL.inc()


# ----------------------------------------------------------------------
# WebScraper – high‑level public API
# ----------------------------------------------------------------------
class WebScraper:
    """
    Main entry point used by the Lumo backend. It loads a campaign
    configuration (selectors, pagination rules, etc.) and orchestrates
    fetching, extraction, caching and metric collection.
    """

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------
    def __init__(self, campaign: str, max_concurrent: int = 5):
        # Load the per‑campaign configuration (YAML, selector, etc.)
        self.cfg = get_campaign_config(campaign)

        # ------------------------------------------------------------------
        # Default BrowserContext configuration – tweak as needed.
        # These values are passed to every BrowserContext the pool creates.
        # ------------------------------------------------------------------
        default_ctx_config = {
            "window_width": 1280,
            "window_height": 1024,
            # Add any other Playwright context options you want as defaults,
            # e.g. "locale": "en-US", "timezone_id": "UTC", etc.
        }

        # Create the shared BrowserPool and keep a reference on the instance.
        # MAX_BROWSERS is defined elsewhere in the module (or you can replace
        # it with a concrete integer, e.g. 5).
        self.pool = BrowserPool(maxsize=MAX_BROWSERS, config=default_ctx_config)

        # ------------------------------------------------------------------
        # The rest of the scraper’s components.
        # ------------------------------------------------------------------
        self.content_extractor = ContentExtractor()
        self.structured_data_extractor = StructuredDataExtractor()
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.cache_service: Optional[CacheService] = None
        self.active_browsers: Set[int] = set()

    @classmethod
    async def create(
        cls,
        campaign: str,
        max_concurrent: int = 5,
        cache_service: Optional[CacheService] = None,
    ) -> "WebScraper":
        """Factory that also wires an optional cache."""
        scraper = cls(campaign, max_concurrent)
        scraper.cache_service = cache_service
        if cache_service:
            await cache_service.connect()
        return scraper

    # ------------------------------------------------------------------
    # Helper: pick first non‑empty selector result
    # ------------------------------------------------------------------
    def _first_match(self, soup: BeautifulSoup, selectors: List[Dict[str, str]]) -> List[Any]:
        """
        Iterate over a list of selector dicts (each containing either ``css`` or ``xpath``)
        and return the first non‑empty result set.
        """
        for sel in selectors:
            if "css" in sel and sel["css"]:
                result = soup.select(sel["css"])
                if result:
                    return result
            elif "xpath" in sel and sel["xpath"]:
                try:
                    from lxml import etree

                    tree = etree.HTML(str(soup))
                    result = tree.xpath(sel["xpath"])
                    if result:
                        return result
                except Exception:
                    continue
        return []

    # ------------------------------------------------------------------
    # List‑page helpers
    # ------------------------------------------------------------------
    def _extract_links(self, page_html: str) -> List[str]:
        """Return absolute URLs found via the campaign's ``link_selectors``."""
        soup = BeautifulSoup(page_html, "html.parser")
        raw = self._first_match(soup, self.cfg["list_page"]["link_selectors"])
        links: List[str] = []
        for el in raw:
            if hasattr(el, "get"):
                href = el.get("href")
                if href:
                    links.append(href)
            elif isinstance(el, str):
                links.append(el)
        return links

    def _has_next_page(self, page_html: str) -> bool:
        """Detect pagination using CSS/XPath selectors or a fallback regex."""
        soup = BeautifulSoup(page_html, "html.parser")
        pag = self.cfg["list_page"].get("pagination", {})

        next_el = self._first_match(
            soup,
            [
                {"css": pag.get("next_css")} if pag.get("next_css") else {},
                {"xpath": pag.get("next_xpath")} if pag.get("next_xpath") else {}
            ],
        )
        if next_el:
            return True

        regex = pag.get("next_url_regex")
        if regex:
            return bool(re.search(regex, page_html))
        return False

    # ------------------------------------------------------------------
    # Detail‑page helpers
    # ------------------------------------------------------------------
    def _extract_profile(self, page_html: str) -> Dict[str, List[str]]:
        """
        Return a mapping ``field_name -> [values...]`` according to the
        ``profile_page.fields`` section of the campaign config.
        """
        soup = BeautifulSoup(page_html, "html.parser")
        fields_cfg = self.cfg.get("profile_page", {}).get("fields", {})
        result: Dict[str, List[str]] = {}

        for field, selectors in fields_cfg.items():
            matches = self._first_match(soup, selectors)
            values: List[str] = []
            for m in matches:
                if hasattr(m, "get_text"):
                    values.append(m.get_text(strip=True))
                elif isinstance(m, str):
                    values.append(m.strip())
            if values:
                result[field] = values
        return result

    # ------------------------------------------------------------------
    # Low‑level page fetch (uses the pooled Selenium browser)
    # ------------------------------------------------------------------
    async def _get_page_content(self, url: str, options: Dict[str, Any]) -> Dict[str, Any]:
        """
        Retrieve raw HTML, optional screenshot and link list.
        Returns a dict compatible with the downstream processing pipeline.
        """
        ctx = await self.browser_pool.get_browser()
        try:
            await ctx.navigate(url, timeout=options.get("timeout", 30))

            # Optional explicit wait for a selector
            if options.get("wait_for_selector"):
                elem = EC.presence_of_element_located(
                    (By.CSS_SELECTOR, options["wait_for_selector"])
                )
                WebDriverWait(ctx.browser, options.get("timeout", 30)).until(elem)

            page_source = await ctx.get_page_source()

            screenshot = None
            if options.get("include_screenshot"):
                screenshot = await ctx.take_screenshot()

            # Gather a flat list of anchor data via JS (fast, no extra round‑trip)
            links = ctx.browser.execute_script(
                """
                return Array.from(document.querySelectorAll('a')).map(a=>({
                    href: a.href,
                    text: a.textContent.trim(),
                    rel: a.rel
                }));
                """
            )

            return {
                "content": page_source,
                "raw_content": page_source if options.get("include_raw_html") else None,
                "status": 200,
                "screenshot": screenshot,
                "links": links,
                "headers": {},  # placeholder – could be filled via CDP if needed
            }
        finally:
            await self.browser_pool.release_browser(ctx)

    # ------------------------------------------------------------------
    # Public scrape entry point
    # ------------------------------------------------------------------
    async def scrape(self, url: str, options: Dict[str, Any]) -> Dict[str, Any]:
        """
        High‑level API used by the Lumo backend.
        Handles caching, concurrency limits, metric collection and
        graceful error reporting.
        """
        SCRAPE_REQUESTS.inc()

        # ------------------- Cache lookup -------------------
        if self.cache_service and not options.get("bypass_cache"):
            cached = await self.cache_service.get_cached_result(url, options)
            if cached:
                return {"success": True, "data": cached, "cached": True}

        # ------------------- Core scraping -------------------
        async with self.semaphore:
            try:
                with SCRAPE_DURATION.time():
                    raw = await self._get_page_content(url, options)
                    processed = await self._process_page_data(raw, options, url)

                # ------------------- Store in cache -------------------
                if self.cache_service and not options.get("bypass_cache"):
                    ttl = options.get(
                        "cache_ttl",
                        getattr(settings, "CACHE_TTL", 86400),
                    )
                    await self.cache_service.cache_result(
                        url,
                        options,
                        processed,
                        ttl=timedelta(seconds=ttl),
                    )

                return {"success": True, "data": processed, "cached": False}
            except Exception as exc:  # pylint: disable=broad-except
                SCRAPE_ERRORS.inc()
                logger.error(f"Scrape failure for {url}: {exc}")
                return {
                    "success": False,
                    "data": {
                        "markdown": None,
                        "html": None,
                        "rawHtml": None,
                        "screenshot": None,
                        "links": None,
                        "actions": None,
                        "metadata": {
                            "title": None,
                            "description": None,
                            "language": None,
                            "sourceURL": url,
                            "statusCode": 500,
                            "error": str(exc),
                        },
                        "llm_extraction": None,
                        "warning": str(exc),
                        "structured_data": None,
                    },
                }

    # ------------------------------------------------------------------
    # Post‑fetch processing (content + structured‑data extraction)
    # ------------------------------------------------------------------
    async def _process_page_data(
        self, page_data: Dict[str, Any], options: Dict[str, Any], url: str
    ) -> Dict[str, Any]:
        """
        Run the heavy‑weight content extractor and the (lighter) structured‑data
        extractor in parallel, then assemble the final response payload.
        """
        try:
            # Content extraction (async)
            content_fut = self.content_extractor.extract_content(
                page_data["content"], options.get("only_main", True)
            )

            # Structured‑data extraction (CPU‑bound, run in thread pool)
            sd_fut = asyncio.get_event_loop().run_in_executor(
                None, self.structured_data_extractor.extract_all, page_data["content"]
            )

            processed_content, structured_data = await asyncio.gather(content_fut, sd_fut)

            # Merge metadata from the content extractor
            metadata = {
                "title": None,
                "description": None,
                "language": None,
                "sourceURL": url,
                "statusCode": page_data["status"],
                "error": None,
            }
            if processed_content.get("metadata"):
                metadata.update(processed_content["metadata"])

            # Normalise link list
            formatted_links = (
                [lnk["href"] for lnk in page_data.get("links", []) if lnk.get("href")]
                if page_data.get("links")
                else None
            )

            return {
                "markdown": processed_content["markdown"],
                "html": processed_content["html"],
                "rawHtml": page_data["raw_content"],
                "screenshot": page_data.get("screenshot"),
                "links": formatted_links,
                "actions": (
                    {"screenshots": [page_data["screenshot"]]}
                    if page_data.get("screenshot")
                    else None
                ),
                "metadata": metadata,
                "llm_extraction": None,
                "warning": None,
                "structured_data": structured_data,
            }
        except Exception as exc:  # pylint: disable=broad-except
            logger.error(f"Error during post‑processing: {exc}")
            raise

    # ------------------------------------------------------------------
    # Graceful shutdown
    # ------------------------------------------------------------------
    async def cleanup(self):
        """Close the browser pool and any attached cache connections."""
        await self.browser_pool.cleanup()
        if self.cache_service:
            await self.cache_service.disconnect()


# ----------------------------------------------------------------------
# Module‑level convenience: a singleton for quick one‑off calls
# ----------------------------------------------------------------------
_default_scraper: Optional[WebScraper] = None


async def get_default_scraper(campaign: str = "default") -> WebScraper:
    """Lazy‑load a shared scraper instance (useful for simple scripts)."""
    global _default_scraper
    if _default_scraper is None:
        _default_scraper = await WebScraper.create(campaign)
    return _default_scraper
