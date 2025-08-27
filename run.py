import os
import json
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    input_path = '/apify/input.json'
    logger.info("Listing contents of /apify directory:")
    try:
        files = os.listdir('/apify')
        logger.info(f"/apify contents: {files}")
    except Exception as e:
        logger.warning(f"Could not list /apify: {e}")

    input_data = {}

    if os.path.exists(input_path):
        try:
            with open(input_path) as f:
                input_data = json.load(f)
            logger.info(f"Loaded input: {input_data}")
        except Exception as e:
            logger.exception(f"Failed to read input.json: {str(e)}")
    else:
        logger.warning("No input.json found. Proceeding without input.")

    url = input_data.get("url")
    max_depth = input_data.get("max_depth", 1)
    max_pages = input_data.get("max_pages", 10)
    campaign = input_data.get("campaign", "default")

    logger.info(f"Running crawl with: URL={url}, max_depth={max_depth}, max_pages={max_pages}, campaign={campaign}")

if __name__ == "__main__":
    main()