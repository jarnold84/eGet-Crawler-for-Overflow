# services/crawler/list_page_crawler.py
"""
Fetches a campaign’s list pages, extracts profile URLs, follows pagination
according to the selectors defined in ``CampaignConfig.list_page``.
"""

import itertools
import logging
from typing import Iterable, Set

import httpx
from bs4 import BeautifulSoup

from .config_loader import get_campaign_config, CampaignNotFoundError
from .config_loader import CampaignConfig  # the Pydantic model

log = logging.getLogger(__name__)

# ----------------------------------------------------------------------
# Helper – apply a list of selectors (CSS or XPath) to a soup object.
# ----------------------------------------------------------------------
def _apply_selectors(soup: BeautifulSoup, selectors):
    """
    Returns a list of strings extracted by the first selector that yields results.
    Supports both CSS (``{'css': '…'}``) and XPath (``{'xpath': '…'}``).
    """
    for sel in selectors:
        if isinstance(sel, dict) and "css" in sel:
            elems = soup.select(sel["css"])
        elif isinstance(sel, dict) and "xpath" in sel:
            # BeautifulSoup doesn’t support XPath natively; fall back to lxml if needed.
            # For the MVP we only handle CSS; raise otherwise.
            raise NotImplementedError("XPath selectors not implemented in MVP")
        else:
            continue

        if elems:
            # Normalise to text or href depending on context.
            return [e.get_text(strip=True) if e.name != "a" else e.get("href") for e in elems]
    return []


# ----------------------------------------------------------------------
# Core generator – yields unique profile URLs for a given campaign.
# ----------------------------------------------------------------------
def iter_profile_urls(campaign_name: str, start_url: str) -> Iterable[str]:
    """
    Walks the list pages for ``campaign_name`` starting at ``start_url``.
    Yields each discovered profile URL exactly once.
    """
    cfg: CampaignConfig = get_campaign_config(campaign_name)

    visited_pages: Set[str] = set()
    discovered_profiles: Set[str] = set()

    next_url = start_url

    while next_url and next_url not in visited_pages:
        log.debug("Fetching list page %s", next_url)
        visited_pages.add(next_url)

        resp = httpx.get(next_url, timeout=10.0)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # ---- Extract profile links -------------------------------------------------
        link_sel = cfg.list_page.link_selectors
        for href in _apply_selectors(soup, link_sel):
            if href and href not in discovered_profiles:
                # Resolve relative URLs against the current page.
                full_url = httpx.URL(href, base=next_url).join(href).human_repr()
                discovered_profiles.add(full_url)
                yield full_url

        # ---- Find the “next page” link -------------------------------------------
        next_sel = cfg.list_page.pagination.next_css or []
        next_candidates = _apply_selectors(soup, [{"css": s} for s in next_sel])
        next_url = next_candidates[0] if next_candidates else None