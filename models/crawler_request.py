# models/crawler_request.py
import re
import uuid
from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, HttpUrl, validator


# ----------------------------------------------------------------------
#  Crawl status enumeration – used by the service to track progress
# ----------------------------------------------------------------------
class CrawlStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


# ----------------------------------------------------------------------
#  Simple stats container – the service updates these while crawling
# ----------------------------------------------------------------------
class CrawlStats(BaseModel):
    pages_scraped: int = 0
    leads_extracted: int = 0
    errors: int = 0
    duration_seconds: float = 0.0


# ----------------------------------------------------------------------
#  Main request model – this is what `run_crawler.py` builds and passes
# ----------------------------------------------------------------------
class CrawlerRequest(BaseModel):
    """
    Request model for the crawler endpoint.

    The fields below are deliberately exhaustive because the crawler
    service reads several of them directly (e.g. ``max_concurrent`` and
    ``campaign_name``).  Feel free to omit any optional field when you
    instantiate the model – Pydantic will fill in the defaults.
    """

    # ------------------------------------------------------------------
    #  Core identifiers
    # ------------------------------------------------------------------
    crawl_id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        description="Unique identifier for the crawl request",
    )
    url: HttpUrl = Field(..., description="Root URL to start crawling from")
    campaign_name: str = Field(..., description="Campaign identifier (e.g. 'mock_campaign')")

    # ------------------------------------------------------------------
    #  Limits & concurrency controls
    # ------------------------------------------------------------------
    max_depth: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Maximum depth to crawl from the root URL",
    )
    max_pages: int = Field(
        default=100,
        ge=1,
        le=1000,
        description="Maximum number of pages to crawl",
    )
    max_concurrent: int = Field(
        default=5,
        ge=1,
        description="Maximum number of simultaneous HTTP requests",
    )
    max_errors: int = Field(
        default=5,
        ge=0,
        description="How many request errors are tolerated before aborting",
    )
    max_time_seconds: int = Field(
        default=60 * 60,
        ge=1,
        description="Hard timeout for the whole crawl (seconds)",
    )

    # ------------------------------------------------------------------
    #  URL filtering (your original regex‑based include/exclude)
    # ------------------------------------------------------------------
    exclude_patterns: List[str] = Field(
        default_factory=list,
        description="Regex patterns for URLs that should be skipped",
    )
    include_patterns: List[str] = Field(
        default_factory=list,
        description="Regex patterns for URLs that must be crawled",
    )
    respect_robots_txt: bool = Field(
        default=True,
        description="Whether to obey robots.txt directives",
    )

    # ------------------------------------------------------------------
    #  Tracking fields – populated by the service as the crawl proceeds
    # ------------------------------------------------------------------
    status: CrawlStatus = Field(
        default=CrawlStatus.PENDING,
        description="Current state of the crawl",
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp when the request object was created",
    )
    started_at: Optional[datetime] = Field(
        default=None,
        description="Timestamp when the crawl actually began",
    )
    completed_at: Optional[datetime] = Field(
        default=None,
        description="Timestamp when the crawl finished (success or failure)",
    )
    stats: CrawlStats = Field(
        default_factory=CrawlStats,
        description="Runtime statistics that the service updates",
    )

    # ------------------------------------------------------------------
    #  Validators – keep your original regex‑validation logic
    # ------------------------------------------------------------------
    @validator("exclude_patterns", "include_patterns", each_item=True)
    def _validate_regex(cls, pattern: str) -> str:
        """Ensure every supplied pattern is a valid regular expression."""
        try:
            re.compile(pattern)
        except re.error as exc:
            raise ValueError(f"Invalid regex pattern '{pattern}': {exc}") from exc
        return pattern

    # ------------------------------------------------------------------
    #  Example payload – useful for API docs / OpenAPI generation
    # ------------------------------------------------------------------
    class Config:
        json_schema_extra = {
            "example": {
                "url": "http://localhost:8000/index.html",
                "campaign_name": "mock_campaign",
                "max_depth": 2,
                "max_pages": 10,
                "max_concurrent": 3,
                "max_errors": 5,
                "max_time_seconds": 3600,
                "exclude_patterns": [r"/api/.*", r".*\.(jpg|jpeg|png|gif)$"],
                "include_patterns": [r"/blog/.*", r"/docs/.*"],
                "respect_robots_txt": True,
            }
        }