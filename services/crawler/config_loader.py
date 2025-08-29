# services/crawler/config_loader.py
"""
Loads the selector configuration from ``configs/selectors.yaml``.
The YAML now has a top‑level ``selectors`` key, so the loader extracts that
mapping before returning a typed ``CampaignConfig``.
"""

import yaml
from pathlib import Path
from typing import List, Optional, TypedDict, Union

# ----------------------------------------------------------------------
# Typed structures – keep them simple and Pylance‑friendly
# ----------------------------------------------------------------------
class CssSelector(TypedDict, total=False):
    css: str


class XPathSelector(TypedDict, total=False):
    xpath: str


# A selector can be either a CSS dict or an XPath dict
Selector = Union[CssSelector, XPathSelector]

# ----------------------------------------------------------------------
# Profile fields
# ----------------------------------------------------------------------
class ProfileFields(TypedDict, total=False):
    name: List[Selector]
    email: List[Selector]
    phone: List[Selector]
    socials: List[Selector]
    title: List[Selector]
    organization: List[Selector]


# ----------------------------------------------------------------------
# Pagination config
# ----------------------------------------------------------------------
class PaginationConfig(TypedDict, total=False):
    next_css: Optional[str]
    next_xpath: Optional[str]
    next_url_regex: Optional[str]


# ----------------------------------------------------------------------
# List‑page config
# ----------------------------------------------------------------------
class ListPageConfig(TypedDict, total=False):
    link_selectors: List[Selector]
    pagination: PaginationConfig


# ----------------------------------------------------------------------
# Profile‑page config
# ----------------------------------------------------------------------
class ProfilePageConfig(TypedDict, total=False):
    fields: ProfileFields


# ----------------------------------------------------------------------
# Whole‑campaign config
# ----------------------------------------------------------------------
class CampaignConfig(TypedDict, total=False):
    list_page: ListPageConfig
    profile_page: ProfilePageConfig


# ----------------------------------------------------------------------
# Public API
# ----------------------------------------------------------------------
# Resolve the path relative to this file (two levels up → project root)
CONFIG_PATH = (
    Path(__file__).resolve().parents[2] / "configs" / "selectors.yaml"
)


def _load_yaml() -> dict:
    """Read the YAML file and return the inner ``selectors`` mapping."""
    with CONFIG_PATH.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
        # The file now wraps everything under a top‑level key called “selectors”
        return raw.get("selectors", {})


# ----------------------------------------------------------------------
# Custom exception for a missing campaign
# ----------------------------------------------------------------------
class CampaignNotFoundError(KeyError):
    """Raised when a requested campaign does not exist in selectors.yaml."""
    def __init__(self, campaign_name: str):
        super().__init__(f"Campaign '{campaign_name}' not found.")
        self.campaign_name = campaign_name


def get_campaign_config(campaign_name: str) -> CampaignConfig:
    """
    Return the configuration for a given campaign.

    Raises:
        CampaignNotFoundError: if the campaign does not exist in the YAML.
    """
    raw_cfg = _load_yaml()
    try:
        # ``raw_cfg`` is a plain dict mapping campaign names → config dicts.
        return raw_cfg[campaign_name]  # type: ignore[return-value]
    except KeyError as exc:
        # Re‑raise a domain‑specific error that callers can catch.
        raise CampaignNotFoundError(campaign_name) from exc


def list_available_campaigns() -> List[str]:
    """Convenient helper for UI / CLI."""
    return list(_load_yaml().keys())