# tests/test_config_loader.py
import pytest

from services.crawler.config_loader import (
    get_campaign_config,
    list_available_campaigns,
    CampaignNotFoundError,
)


def test_all_campaigns_have_required_sections():
    """
    Sanity‑check that iterates over every campaign defined in
    ``configs/selectors.yaml`` and verifies the minimal structure.
    """
    for name in list_available_campaigns():
        cfg = get_campaign_config(name)

        # Every campaign must define a list_page section.
        assert "list_page" in cfg, f"{name} missing list_page"

        # list_page must contain at least one link selector.
        assert cfg["list_page"].get("link_selectors"), f"{name} missing link selectors"

        # profile_page is optional – if present it must contain at least one field.
        if "profile_page" in cfg:
            fields = cfg["profile_page"].get("fields", {})
            assert fields, f"{name} profile_page has no fields"


def test_successful_retrieval_of_known_campaign():
    """
    Pick the first campaign from the catalogue and ensure that the loader
    returns a dictionary that contains the expected top‑level keys.
    """
    known_name = list_available_campaigns()[0]  # there is at least one campaign
    cfg = get_campaign_config(known_name)

    # The returned object should be a dict (TypedDict at runtime is a plain dict).
    assert isinstance(cfg, dict)

    # Verify the mandatory sections are present for this concrete campaign.
    assert "list_page" in cfg
    assert cfg["list_page"].get("link_selectors")


def test_unknown_campaign_raises_custom_error():
    """
    Request a campaign that does not exist and confirm that the
    domain‑specific ``CampaignNotFoundError`` is raised.
    """
    unknown_name = "this_campaign_does_not_exist_12345"
    with pytest.raises(CampaignNotFoundError) as exc_info:
        get_campaign_config(unknown_name)

    # The error message should contain the missing name for easier debugging.
    assert unknown_name in str(exc_info.value)


# ----------------------------------------------------------------------
# Parametrized test – generated from the actual selector file
# ----------------------------------------------------------------------
# Grab the first few campaigns (or all, if you prefer) and assert that each
# contains the mandatory ``list_page`` section.
_CAMPAIGN_PARAMS = [
    (name, ["list_page"]) for name in list_available_campaigns()[:3]
]  # adjust slice size as desired


@pytest.mark.parametrize("campaign_name,required_keys", _CAMPAIGN_PARAMS)
def test_parametrized_campaigns(campaign_name, required_keys):
    """
    Dynamically generated parametrized test that validates a handful of
    known campaigns.  It confirms that each campaign includes the required
    top‑level sections.
    """
    cfg = get_campaign_config(campaign_name)

    for key in required_keys:
        assert key in cfg, f"{campaign_name} missing required section '{key}'"
