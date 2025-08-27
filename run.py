import os
import json
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    input_path = '/apify/input.json'
    
    logger.info("📂 Checking /apify directory...")
    try:
        files = os.listdir('/apify')
        logger.info(f"📁 /apify contents: {files}")
    except Exception as e:
        logger.warning(f"⚠️ Could not list /apify directory: {e}")

    input_data = {}

    if os.path.exists(input_path):
        try:
            with open(input_path, 'r') as f:
                input_data = json.load(f)
            logger.info(f"✅ Loaded input.json: {json.dumps(input_data, indent=2)}")
        except Exception as e:
            logger.exception(f"❌ Failed to parse input.json: {e}")
    else:
        logger.warning("⚠️ No input.json found. Proceeding with default values.")

    # Handle camelCase input keys (as used by Apify input schema UI)
    url = input_data.get("url")
    max_depth = input_data.get("maxDepth", 1)
    max_pages = input_data.get("maxPages", 10)
    campaign = input_data.get("campaign", "default")

    # Log final values used in crawl
    logger.info(f"🚀 Running crawl with:\n"
                f"🔗 URL: {url}\n"
                f"📚 Max Depth: {max_depth}\n"
                f"📄 Max Pages: {max_pages}\n"
                f"🏷️ Campaign: {campaign}")

    # TODO: Replace this with your actual crawl logic
    # crawl_site(url, max_depth=max_depth, max_pages=max_pages, campaign=campaign)

if __name__ == "__main__":
    main()
