# services/crawler/profile_extractor.py
"""
Given a profile URL and a campaign name, extracts the fields defined in
``CampaignConfig.profile_page.fields`` and returns a ``Lead`` model.
"""

import logging
from typing import Dict, List, Optional

import httpx
from bs4 import BeautifulSoup

from .config_loader import get_campaign_config, CampaignConfig

# ------------------- IMPORT FIXED -------------------
# Choose ONE of the two lines below (remove the other).

# 1️⃣ Relative import (requires __init__.py in parent packages)
# from ..models.lead import Lead

# 2️⃣ Absolute import (also works once the package is on PYTHONPATH)
from services.models.lead import Lead
# --------------------------------------------------

log = logging.getLogger(__name__)

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
            # Prefer the href attribute for links, otherwise text.
            if elem.name == "a":
                val = elem.get("href")
            else:
                val = elem.get_text(strip=True)
            if val:
                return val
    return None


# ----------------------------------------------------------------------
def extract_lead(campaign_name: str, profile_url: str) -> Lead:
    """
    Fetches ``profile_url`` and builds a ``Lead`` according to the selectors
    defined for ``campaign_name``.
    """
    cfg: CampaignConfig = get_campaign_config(campaign_name)

    resp = httpx.get(profile_url, timeout=10.0)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    fields_cfg = cfg.profile_page.fields if cfg.profile_page else None
    data: Dict[str, Optional[str]] = {}

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
                data[field_name] = _extract_one_field(soup, selectors)

    return Lead(
        source_url=profile_url,
        name=data.get("name"),
        title=data.get("title"),
        email=data.get("email"),
        phone=data.get("phone"),
        socials=data.get("socials"),
        organization=data.get("organization"),
    )