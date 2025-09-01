# services/crawler/config_loader.py
"""
Loads the selector configuration from ``configs/selectors.yaml`` and validates it
with Pydantic models.  The file can contain a top‑level ``selectors`` key or
just the mapping of campaign names → config dictionaries.

The public API mirrors the original version:
* ``get_campaign_config(name)`` – returns a validated ``CampaignConfig`` or
  raises ``CampaignNotFoundError``.
* ``list_available_campaigns()`` – convenience helper for UI/CLI.
"""

import yaml
from pathlib import Path
from typing import List, Dict

# ----------------------------------------------------------------------
# Pydantic schemas – they give us runtime validation and nice error msgs
# ----------------------------------------------------------------------
from pydantic import BaseModel, Field, ValidationError


class CssSelector(BaseModel):
    """Simple CSS selector representation."""
    css: str


class XPathSelector(BaseModel):
    """Simple XPath selector representation."""
    xpath: str


# A selector can be either a CSS dict or an XPath dict
Selector = CssSelector | XPathSelector


class ProfileFields(BaseModel):
    """Mapping of lead fields → list of selectors (CSS or XPath)."""
    name: List[Selector] = Field(default_factory=list)
    email: List[Selector] = Field(default_factory=list)
    phone: List[Selector] = Field(default_factory=list)
    socials: List[Selector] = Field(default_factory=list)
    title: List[Selector] = Field(default_factory=list)
    organization: List[Selector] = Field(default_factory=list)


class PaginationConfig(BaseModel):
    """How to discover the next page on a list view."""
    next_css: str | None = None
    next_xpath: str | None = None
    next_url_regex: str | None = None


class ListPageConfig(BaseModel):
    """Selectors that drive the list‑page crawl."""
    link_selectors: List[Selector] = Field(default_factory=list)
    pagination: PaginationConfig = Field(default_factory=PaginationConfig)


class ProfilePageConfig(BaseModel):
    """Selectors that extract fields from a profile page."""
    fields: ProfileFields = Field(default_factory=ProfileFields)


class CampaignConfig(BaseModel):
    """Complete configuration for a single campaign."""
    list_page: ListPageConfig = Field(default_factory=ListPageConfig)
    profile_page: ProfilePageConfig = Field(default_factory=ProfilePageConfig)


class AllCampaigns(BaseModel):
    """Top‑level container – maps campaign name → its config."""
    campaigns: Dict[str, CampaignConfig]


# ----------------------------------------------------------------------
# Internal helpers & caching
# ----------------------------------------------------------------------
# Resolve the path relative to this file (two levels up → project root)
CONFIG_PATH = (
    Path(__file__).resolve().parents[2] / "configs" / "selectors.yaml"
)

# Simple in‑process cache so the YAML is read/validated only once per process
_cached_all: AllCampaigns | None = None


def _load_yaml() -> dict:
    """Read the YAML file and return the inner ``selectors`` mapping."""
    with CONFIG_PATH.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
        # If the file wraps everything under a top‑level key called “selectors”,
        # return that inner dict; otherwise return the whole dict.
        return raw.get("selectors", raw)


def _load_all() -> AllCampaigns:
    """
    Parse the entire YAML, validate it against ``AllCampaigns`` and cache the
    result.  Any validation problem raises ``ValidationError`` with a clear
    description of the offending field.
    """
    global _cached_all
    if _cached_all is None:
        raw = _load_yaml()
        # The YAML format we expect is: {campaign_name: {...config...}, ...}
        # Wrap it under the ``campaigns`` key so the Pydantic model matches.
        wrapped = {"campaigns": raw}
        _cached_all = AllCampaigns(**wrapped)   # validation happens here
    return _cached_all


# ----------------------------------------------------------------------
# Custom exception for a missing campaign
# ----------------------------------------------------------------------
class CampaignNotFoundError(KeyError):
    """Raised when a requested campaign does not exist in selectors.yaml."""

    def __init__(self, campaign_name: str):
        super().__init__(f"Campaign '{campaign_name}' not found.")
        self.campaign_name = campaign_name


# ----------------------------------------------------------------------
# Public API
# ----------------------------------------------------------------------
def get_campaign_config(campaign_name: str) -> CampaignConfig:
    """
    Return a **validated** ``CampaignConfig`` for the requested campaign.

    Raises
    ------
    CampaignNotFoundError
        If the campaign name is not present in the YAML.
    ValidationError
        If the YAML exists but does not conform to the Pydantic schema.
    """
    all_cfg = _load_all()
    try:
        return all_cfg.campaigns[campaign_name]
    except KeyError as exc:
        raise CampaignNotFoundError(campaign_name) from exc


def list_available_campaigns() -> List[str]:
    """Convenient helper for UI / CLI – returns all campaign identifiers."""
    return list(_load_all().campaigns.keys())