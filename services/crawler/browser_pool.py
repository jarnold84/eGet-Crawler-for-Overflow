# scripts/check_browser_pool.py
import asyncio, sys
from pathlib import Path

# ensure repo root is on sys.path
repo_root = Path(__file__).resolve().parents[1]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from services.scraper.scraper import BrowserPool

async def main():
    pool = BrowserPool(max_browsers=1)
    ctx = await pool.get_browser()
    await ctx.browser.get("https://example.com")
    print("✅ Title:", await ctx.browser.title)
    await pool.release_browser(ctx)
    await pool.cleanup()

if __name__ == "__main__":
    asyncio.run(main())