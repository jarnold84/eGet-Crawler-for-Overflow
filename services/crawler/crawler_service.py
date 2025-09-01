# services/crawler/crawler_service.py
from typing import Dict, List
import asyncio
import uuid
from datetime import datetime
from loguru import logger
from concurrent.futures import ThreadPoolExecutor

# ----------------------------------------------------------------------
#  External services / helpers
# ----------------------------------------------------------------------
from services.scraper.scraper import WebScraper
from .link_extractor import LinkExtractor
from .queue_manager import QueueManager
from .profile_extractor import extract_lead          # <-- NEW
from models.lead import Lead                       # <-- NEW
from models.crawler_request import CrawlerRequest
from models.crawler_response import (
    CrawlerResponse,
    CrawlStats,
    CrawledPage,
    CrawlStatus,
)

# ----------------------------------------------------------------------
#  CrawlerService – production‑grade orchestrator
# ----------------------------------------------------------------------
class CrawlerService:
    """
    Production‑grade crawler service that orchestrates web crawling,
    extracts a Lead from each visited page and persists it.
    """

    def __init__(self, max_concurrent: int = 5, worker_threads: int = 3):
        self.max_concurrent = max_concurrent
        self.worker_threads = worker_threads
        self.scraper = WebScraper(max_concurrent=max_concurrent)
        self.active_crawls: Dict[uuid.UUID, CrawlerResponse] = {}
        self._lock = asyncio.Lock()
        self._executor = ThreadPoolExecutor(max_workers=worker_threads)
        self._semaphore = asyncio.Semaphore(max_concurrent)

    # ------------------------------------------------------------------
    #  Persistence stub – replace with DB/CSV/queue when ready
    # ------------------------------------------------------------------
    @staticmethod
    def _save_lead(lead: Lead) -> None:
        """
        Persist a Lead record.

        For the MVP we simply dump the JSON to stdout.
        Swap this out for a real storage implementation later.
        """
        print("\n🗂️  Persisted Lead →", lead.json(indent=2))

    # ------------------------------------------------------------------
    async def _process_page(
        self,
        url: str,
        depth: int,
        queue_manager: QueueManager,
        link_extractor: LinkExtractor,
        response: CrawlerResponse,
        request: CrawlerRequest,
    ) -> None:
        """Process a single page: scrape, extract links, build Lead, persist."""
        try:
            logger.debug(f"Processing {url} at depth {depth}")

            # --------------------------------------------------------------
            # 1️⃣ Scrape the page (via the shared WebScraper)
            # --------------------------------------------------------------
            scrape_result = await self.scraper.scrape(
                url,
                {
                    "only_main": True,
                    "include_raw_html": False,
                    "include_screenshot": False,
                },
            )

            if not scrape_result["success"]:
                async with self._lock:
                    response.stats.failed_count += 1
                logger.error(f"Failed to scrape {url}")
                return

            # --------------------------------------------------------------
            # 2️⃣ Build the generic CrawledPage (unchanged)
            # --------------------------------------------------------------
            page = CrawledPage(
                url=url,
                markdown=scrape_result["data"]["markdown"],
                structured_data=scrape_result["data"].get("structured_data"),
                scrape_id=uuid.uuid4(),
                depth=depth,
            )

            # --------------------------------------------------------------
            # 3️⃣ Extract a Lead from the same page (new step)
            # --------------------------------------------------------------
            lead: Lead | None = None
            try:
                lead = extract_lead(request.campaign_name, url)
            except Exception as exc:  # pragma: no cover – defensive
                logger.error(
                    f"Lead extraction failed for {url} (campaign={request.campaign_name}): {exc}"
                )

            # --------------------------------------------------------------
            # 4️⃣ Persist the Lead (MVP stub) and store it in the response
            # --------------------------------------------------------------
            if lead is not None:
                self._save_lead(lead)                     # <-- persistence
                # Lazily ensure the attribute exists (backward compatible)
                if not hasattr(response, "leads"):
                    response.leads = []                    # type: ignore[attr-defined]
                response.leads.append(lead)               # type: ignore[attr-defined]

            # --------------------------------------------------------------
            # 5️⃣ Extract further links if we haven’t reached max depth
            # --------------------------------------------------------------
            if depth < request.max_depth:
                new_links = link_extractor.extract_links(
                    scrape_result["data"]["html"], url
                )
                async with self._lock:
                    for link in new_links:
                        await queue_manager.add_url(link, depth + 1, url)

            # --------------------------------------------------------------
            # 6️⃣ Record the successful page scrape
            # --------------------------------------------------------------
            async with self._lock:
                response.pages.append(page)
                response.stats.success_count += 1
                logger.info(f"Successfully processed {url}")

        except Exception as e:  # pragma: no cover – unexpected failures
            async with self._lock:
                response.stats.failed_count += 1
            logger.error(f"Error processing {url}: {str(e)}")

        finally:
            await queue_manager.mark_complete(url)

    # ------------------------------------------------------------------
    async def crawl_sync(self, request: CrawlerRequest) -> CrawlerResponse:
        """
        Perform a synchronous crawl (awaitable) and wait for completion.
        Returns a populated CrawlerResponse that now includes ``leads``.
        """
        logger.info(f"Starting synchronous crawl for {request.url}")

        # Initialise helpers
        queue_manager = QueueManager(request)
        link_extractor = LinkExtractor(request)

        # Base response object
        response = CrawlerResponse(
            crawl_id=request.crawl_id,
            status=CrawlStatus.IN_PROGRESS,
            stats=CrawlStats(
                total_pages=0,
                success_count=0,
                failed_count=0,
                skipped_count=0,
                start_time=datetime.utcnow(),
            ),
        )

        try:
            # Seed the queue with the starting URL
            await queue_manager.add_url(str(request.url))

            while True:
                # ------------------------------------------------------------------
                # Termination checks
                # ------------------------------------------------------------------
                if queue_manager.is_complete:
                    logger.debug("Queue is complete – exiting loop")
                    break

                if len(response.pages) >= request.max_pages:
                    logger.info(f"Reached max pages limit: {request.max_pages}")
                    break

                # ------------------------------------------------------------------
                # Pull a batch of URLs to process (respecting worker threads)
                # ------------------------------------------------------------------
                processing_urls: List[str] = []
                async with self._lock:
                    remaining = request.max_pages - len(response.pages)
                    batch_size = min(self.worker_threads, remaining)

                    for _ in range(batch_size):
                        url = await queue_manager.get_next_url()
                        if url:
                            processing_urls.append(url)

                if not processing_urls:
                    # Nothing ready yet – wait a tick and retry
                    if not queue_manager.in_progress and queue_manager.queue.empty():
                        logger.debug("No URLs left and nothing in‑flight – breaking")
                        break
                    await asyncio.sleep(0.1)
                    continue

                # ------------------------------------------------------------------
                # Fire off concurrent page processors
                # ------------------------------------------------------------------
                tasks = [
                    asyncio.create_task(
                        self._process_page(
                            url=url,
                            depth=queue_manager.get_depth(url),
                            queue_manager=queue_manager,
                            link_extractor=link_extractor,
                            response=response,
                            request=request,
                        )
                    )
                    for url in processing_urls
                ]

                if tasks:
                    await asyncio.gather(*tasks)
                    logger.debug(f"Processed batch of {len(tasks)} URLs")

            # ------------------------------------------------------------------
            # Final statistics
            # ------------------------------------------------------------------
            response.status = CrawlStatus.COMPLETED
            response.stats.end_time = datetime.utcnow()
            response.stats.duration_seconds = (
                response.stats.end_time - response.stats.start_time
            ).total_seconds()
            response.stats.total_pages = len(response.pages)

            logger.info(
                f"Crawl completed – {len(response.pages)} pages, "
                f"{len(getattr(response, 'leads', []))} leads in {response.stats.duration_seconds:.2f}s"
            )
            return response

        except Exception as e:  # pragma: no cover – unexpected fatal error
            logger.exception(f"Crawl failed: {str(e)}")
            response.status = CrawlStatus.FAILED
            response.error = str(e)
            return response

    # ------------------------------------------------------------------
    async def start_crawl(self, request: CrawlerRequest) -> CrawlerResponse:
        """
        Kick off an asynchronous crawl that runs in the background.
        Useful for a web‑API where you want to return immediately.
        """
        logger.info(f"Starting asynchronous crawl for {request.url}")

        response = CrawlerResponse(
            crawl_id=request.crawl_id,
            status=CrawlStatus.IN_PROGRESS,
            stats=CrawlStats(
                total_pages=0,
                success_count=0,
                failed_count=0,
                skipped_count=0,
                start_time=datetime.utcnow(),
            ),
        )

        self.active_crawls[request.crawl_id] = response
        asyncio.create_task(self.crawl_sync(request))
        return response

    # ------------------------------------------------------------------
    async def cleanup(self):
        """Gracefully shut down thread pool and scraper."""
        try:
            self._executor.shutdown(wait=False)
            await self.scraper.cleanup()
            self.active_crawls.clear()
        except Exception as e:  # pragma: no cover – defensive
            logger.error(f"Error during cleanup: {str(e)}")