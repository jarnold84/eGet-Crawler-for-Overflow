import asyncio
from services.scraper.scraper import get_default_scraper

async def main():
    scraper = await get_default_scraper("default")   # use a real campaign name
    result = await scraper.scrape(
        "https://example.com",
        {"wait_for_selector": "body", "include_screenshot": False},
    )
    print("✅", result.get("success"))
    await scraper.cleanup()

asyncio.run(main())
