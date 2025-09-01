import time
import asyncio
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from contextlib import asynccontextmanager
from prometheus_client import make_asgi_app
from loguru import logger

from core.config import settings
from core.exceptions import ScraperException, ValidationError
from models.request import ScrapeRequest
from services.cache.cache_service import CacheService
from services.scraper.scraper import WebScraper
from services.crawler.crawler_service import CrawlerService
from api.v1.endpoints import crawler, scraper, chunker, converter

# --------------------------------------------------------------
# NEW IMPORT – campaign loader & custom exception
# --------------------------------------------------------------
from services.crawler.config_loader import (
    get_campaign_config,
    CampaignNotFoundError,
)

# Prometheus metrics endpoint
metrics_app = make_asgi_app()

logger.info(f"Loaded user agent: {settings.DEFAULT_USER_AGENT}")

# ------------------------------------------------------------------
# If running on Apify, run actor input directly
# ------------------------------------------------------------------
# ------------------------------------------------------------------
# Optional Apify integration – only needed when the APIFY_TOKEN env var is set.
# The import is wrapped so the code works even when the `apify` package
# isn’t installed (e.g., during local development or CI runs).
# ------------------------------------------------------------------
try:
    from apify import Actor  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover
    # Define a very small stub so type‑checkers don’t complain later.
    # The stub only implements the async context‑manager protocol used below.
    class _DummyActor:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        @staticmethod
        async def get_input():  # returns None to indicate “no Apify payload”
            return None

        @staticmethod
        async def push_data(_: dict):
            # In a non‑Apify environment we simply ignore the call.
            return None

    Actor = _DummyActor  # type: ignore[assignment]

    async def apify_run():
        async with Actor:
            input_data = await Actor.get_input()
            if input_data is None:
                logger.error("No input received by Apify actor.")
                return

            url = input_data.get("url")
            max_depth = input_data.get("max_depth", 1)
            max_pages = input_data.get("max_pages", 10)
            campaign = input_data.get("campaign", "default")

            logger.info(
                f"Running Apify crawl with: "
                f"URL={url}, max_depth={max_depth}, max_pages={max_pages}, campaign={campaign}"
            )

            # ----------------------------------------------------------
            # VALIDATE CAMPAIGN – raise a clear error if unknown
            # ----------------------------------------------------------
            try:
                # This will raise CampaignNotFoundError if the name is absent.
                cfg = get_campaign_config(campaign)

                # ------------------------------------------------------------------
                # Use the variable so the linter is satisfied and we get a helpful log.
                # ------------------------------------------------------------------
                # DEBUG level – you can raise the level in production if you don’t want
                # this to appear in normal logs.
                logger.debug(
                    "✅ Loaded campaign configuration for '%s' (selectors: %s)",
                    campaign,
                    cfg,
                )
            except CampaignNotFoundError as exc:
                # Log the problem and surface it via the Apify dataset.
                logger.error("❌ Campaign validation failed: %s", exc)

                await Actor.push_data(
                    {
                        "status": "failed",
                        "error": str(exc),
                        "url": url,
                        "campaign": campaign,
                    }
                )

                # Early‑exit – nothing else to do for an invalid campaign.
                return

            # ------------------------------------------------------------------
            # Your real scraping logic would go here, now that we know the
            # campaign is valid.  For demo purposes we just echo the inputs.
            # ------------------------------------------------------------------
            await Actor.push_data(
                {
                    "status": "success",
                    "message": f"Received URL: {url}",
                    "max_depth": max_depth,
                    "max_pages": max_pages,
                    "campaign": campaign,
                }
            )

    if __name__ == "__main__":
        asyncio.run(apify_run())

else:
    # ------------------------------------------------------------------
    # FastAPI App Lifecycle (unchanged)
    # ------------------------------------------------------------------
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        try:
            logger.info("Initializing application...")

            cache_service = CacheService(settings.REDIS_URL)
            await cache_service.connect()

            app.state.scraper = await WebScraper.create(
                max_concurrent=settings.CONCURRENT_SCRAPES,
                cache_service=cache_service,
            )

            app.state.crawler = CrawlerService(
                max_concurrent=settings.CONCURRENT_SCRAPES
            )

            yield

            logger.info("Shutting down application...")
            await app.state.scraper.cleanup()

        except Exception as e:
            logger.exception(f"Application lifecycle error: {str(e)}")
            raise

    app = FastAPI(
        title=settings.PROJECT_NAME,
        description="Production‑grade web scraper API",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_HOSTS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=settings.ALLOWED_HOSTS,
    )

    app.include_router(crawler.router, prefix="/api/v1", tags=["crawler"])
    app.include_router(scraper.router, prefix="/api/v1", tags=["scraper"])
    app.include_router(chunker.router, prefix="/api/v1", tags=["chunker"])
    app.include_router(converter.router, prefix="/api/v1", tags=["converter"])

    @app.middleware("http")
    async def add_timing_header(request: Request, call_next):
        start_time = time.perf_counter()
        response = await call_next(request)
        process_time = time.perf_counter() - start_time
        response.headers["X-Process-Time"] = str(process_time)
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ):
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=ValidationError(errors=exc.errors()).to_dict(),
        )

    @app.exception_handler(ScraperException)
    async def scraper_exception_handler(request: Request, exc: ScraperException):
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.to_dict(),
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        logger.error(f"Unhandled exception: {str(exc)}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": {
                    "code": "INTERNAL_SERVER_ERROR",
                    "message": "An unexpected error occurred",
                    "status": 500,
                }
            },
        )

    app.mount("/metrics", metrics_app)

    @app.get("/health")
    async def health_check():
        return {"status": "healthy", "timestamp": time.time()}

    @app.get("/")
    async def root():
        return {
            "name": settings.PROJECT_NAME,
            "version": "1.0.0",
            "description": "Production‑grade web scraper API",
            "docs_url": "/docs",
            "health_check": "/health",
        }

    @app.post("/scrape", response_model_exclude_none=True)
    async def scrape_url(request: ScrapeRequest, req: Request):
        logger.info(f"Processing scrape request for URL: {request.url}")

        options = {
            "only_main": request.onlyMainContent,
            "timeout": request.timeout or settings.TIMEOUT,
            "user_agent": settings.DEFAULT_USER_AGENT,
            "headers": request.headers,
            "screenshot": True,
            "screenshot_quality": settings.SCREENSHOT_QUALITY,
            "wait_for_selector": request.waitFor,
        }

        if request.actions:
            options["actions"] = request.actions

        result = await req.app.state.scraper.scrape(str(request.url), options)
        return result

    if __name__ == "__main__":
        import uvicorn

        uvicorn.run(
            "main:app",
            host="0.0.0.0",
            port=settings.PORT,
            reload=settings.DEBUG,
            workers=settings.WORKERS,
            log_level=settings.LOG_LEVEL.lower(),
        )
