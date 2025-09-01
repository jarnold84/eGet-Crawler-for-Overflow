# services/crawler/profile_extractor.py
"""
Given a profile URL and a campaign name, extracts the fields defined in
``CampaignConfig.profile_page.fields`` and returns a ``Lead`` model.
"""

import logging
import os
import sys
from typing import Dict, List, Optional

import httpx
from bs4 import BeautifulSoup

from .config_loader import get_campaign_config, CampaignConfig

log = logging.getLogger(__name__)

# ------------------------------------------------------------
#  Import the Lead factory – the model lives in the top‑level `models` package
# ------------------------------------------------------------
from models.lead_factory import lead_from_mapping

# ----------------------------------------------------------------------
def _extract_one_field(soup: BeautifulSoup, selectors: List[dict]) -> Optional[str]:
    """
    Returns the first non‑empty string found by the supplied selectors.
    """
    for sel in selectors:
        if "css" in sel:
            elem = soup.select_one(sel["css"])
        elif "xpath" in sel:
            raise NotImplementedError("XPath not supported in MVP")
        else:
            continue

        if elem:
            # Prefer href for <a>, otherwise text.
            if elem.name == "a":
                val = elem.get("href")
            else:
                val = elem.get_text(strip=True)
            if val:
                return val
    return None


# ----------------------------------------------------------------------
def extract_lead(campaign_name: str, profile_url: str):
    """
    Fetches ``profile_url`` and builds a ``Lead`` according to the selectors
    defined for ``campaign_name``.
    """
    cfg: CampaignConfig = get_campaign_config(campaign_name)

    # ------------------------------------------------------------------
    # 1️⃣ Retrieve the page
    # ------------------------------------------------------------------
    resp = httpx.get(profile_url, timeout=10.0)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    # ------------------------------------------------------------------
    # 2️⃣ Apply the campaign’s selectors
    # ------------------------------------------------------------------
    fields_cfg = cfg.profile_page.fields if cfg.profile_page else None
    raw_fields: Dict[str, Optional[str]] = {}

    if fields_cfg:
        for field_name in (
            "name",
            "title",
            "email",
            "phone",
            "socials",
            "organization",
        ):
            selectors = getattr(fields_cfg, field_name, [])
            if selectors:
                raw_fields[field_name] = _extract_one_field(soup, selectors)

    # ------------------------------------------------------------------
    # 3️⃣ Build the Lead via the factory (handles validation & filtering)
    # ------------------------------------------------------------------
    # Always include the source URL – the factory will ignore unknown keys.
    raw_fields["source_url"] = profile_url
    lead = lead_from_mapping(raw_fields)

    return lead