# tests/test_config_loader.py
from services.crawler.config_loader import (
    get_campaign_config,
    list_available_campaigns,
)

def test_all_campaigns_have_required_sections():
    for name in list_available_campaigns():
        cfg = get_campaign_config(name)
        assert "list_page" in cfg, f"{name} missing list_page"
        # list_page must have at least one link selector
        assert cfg["list_page"].get("link_selectors"), f"{name} missing link selectors"

        # profile_page is optional for campaigns that only crawl list pages
        if "profile_page" in cfg:
            fields = cfg["profile_page"].get("fields", {})
            # ensure at least one field is defined
            assert fields, f"{name} profile_page has no fields"