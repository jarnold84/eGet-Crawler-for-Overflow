# services/crawler/schemas.py
from typing import List, Dict
from pydantic import BaseModel, Field

class ProfileFieldSelectors(BaseModel):
    """CSS‑selector lists for each lead field."""
    name: List[str] = Field(default_factory=list)
    title: List[str] = Field(default_factory=list)
    email: List[str] = Field(default_factory=list)
    phone: List[str] = Field(default_factory=list)

class CampaignConfig(BaseModel):
    """Configuration for a single campaign."""
    list_link_selectors: List[str]
    next_page_selectors: List[str]
    profile_field_selectors: ProfileFieldSelectors

class AllCampaigns(BaseModel):
    """Top‑level container – maps campaign name → config."""
    campaigns: Dict[str, CampaignConfig]