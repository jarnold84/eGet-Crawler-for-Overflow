# run_crawler.py
import asyncio
import uuid
import sys
from pathlib import Path

# Make the repo root importable (same as before)
repo_root = Path(__file__).resolve().parent
if str(repo_root) not in sys.path:
    sys.path.append(str(repo_root))

# Import the service and request model
from services.crawler.crawler_service import CrawlerService
from models.crawler_request import CrawlerRequest

async def main() -> None:
    req = CrawlerRequest(
        crawl_id=uuid.uuid4(),
        url="http://localhost:8000/index.html",
        campaign_name="default",   # <-- this is the same name you used in the YAML config
        max_depth=2,
        max_pages=10,
        max_concurrent=3,
    )

    # NOTE: we now pass the campaign name to the service as well
    svc = CrawlerService(campaign_name=req.campaign_name, max_concurrent=req.max_concurrent)
    resp = await svc.crawl_sync(req)

    print("\n=== CRAWL SUMMARY ===")
    print(f"Pages scraped   : {len(resp.pages)}")
    print(f"Leads extracted: {len(getattr(resp, 'leads', []))}")

    if getattr(resp, "leads", []):
        print("\nFirst lead JSON:")
        print(resp.leads[0].json(indent=2))

if __name__ == "__main__":
    asyncio.run(main())