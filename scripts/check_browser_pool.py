import asyncio
import sys
from pathlib import Path

# -------------------------------------------------------------------------
# Ensure the repository root (the folder that contains the top‑level
# `services` package) is on the import search path.
#
#   repo_root/
#   ├─ services/
#   │   ├─ scraper/
#   │   └─ crawler/
#   └─ scripts/
#
# When we run this file as a script, Python’s default sys.path contains
# the directory of the script (`scripts/`).  We need to prepend the
# repository root so that `import services...` resolves correctly.
# -------------------------------------------------------------------------
repo_root = Path(__file__).resolve().parents[1]   # `scripts/..` → repo root
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

# Now we can import the BrowserPool class that lives in
# services/scraper/scraper.py
from services.scraper.scraper import BrowserPool   # ← the class you kept

async def main() -> None:
    # One‑browser pool is enough for a quick sanity test.
    pool = BrowserPool(max_browsers=1)

    try:
        # Acquire a browser, navigate, read the title.
        ctx = await pool.get_browser()
        await ctx.browser.get("https://example.com")
        title = await ctx.browser.title
        print("✅ Page title fetched:", title)

        # Return the browser to the pool.
        await pool.release_browser(ctx)

    finally:
        # Always clean up – this closes the Chrome process.
        await pool.cleanup()

if __name__ == "__main__":
    # asyncio.run() creates an event loop, runs `main`, and closes the loop.
    asyncio.run(main())