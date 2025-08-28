# services/crawler/browser_pool.py
"""
A tiny, async‑compatible pool of Selenium browsers.

The real implementation would probably:
* launch a limited number of headless Chrome instances,
* hand out a wrapper/context object that knows how to navigate,
* recycle the browser when released,
* close everything on cleanup.

For now we provide a **stub** that satisfies the type‑checker and
allows the rest of the scraper to be exercised.  Replace the
NotImplementedError with your actual pool logic when you’re ready.
"""

import asyncio
from typing import Any

class BrowserPool:
    """Async‑friendly pool that limits concurrent browsers."""

    def __init__(self, max_browsers: int = 5):
        self._max = max_browsers
        self._semaphore = asyncio.Semaphore(max_browsers)

    async def get_browser(self) -> Any:
        """
        Acquire a browser/context.

        In the stub we just acquire the semaphore and raise
        ``NotImplementedError`` – the caller will see the error and
        know the real pool isn’t wired up yet.
        """
        await self._semaphore.acquire()
        raise NotImplementedError(
            "BrowserPool.get_browser() is a stub – implement real Chrome context here."
        )

    async def release_browser(self, ctx: Any) -> None:
        """Return a previously‑acquired browser/context to the pool."""
        # In a real pool you’d close or recycle ``ctx`` here.
        self._semaphore.release()

    async def cleanup(self) -> None:
        """Close any lingering browsers – noop for the stub."""
        # Real implementation would quit all Chrome instances.
        pass