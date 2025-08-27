import logging
import json
from apify import Actor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main():
    await Actor.init()
    
    input_data = await Actor.get_input() or {}
    logger.info(f"✅ Loaded input.json: {json.dumps(input_data, indent=2)}")

    url = input_data.get("url")
    max_depth = input_data.get("maxDepth", 1)
    max_pages = input_data.get("maxPages", 10)
    campaign = input_data.get("campaign", "default")

    logger.info(f"🚀 Running crawl with:\n"
                f"🔗 URL: {url}\n"
                f"📚 Max Depth: {max_depth}\n"
                f"📄 Max Pages: {max_pages}\n"
                f"🏷️ Campaign: {campaign}")

    # TODO: call your actual scraping function
    # await crawl_site(url, max_depth, max_pages, campaign)

    await Actor.exit()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
