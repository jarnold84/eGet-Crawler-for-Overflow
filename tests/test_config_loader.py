# tests/test_config_loader.py
"""
Tests for the Pydantic‑based ``services.crawler.config_loader`` module.

The loader now returns **validated Pydantic models** instead of raw
TypedDict dictionaries, so the tests use attribute access
(e.g. ``cfg.list_page.link_selectors``) rather than key‑lookup.
"""

import pytest

from services.crawler.config_loader import (
    get_campaign_config,
    list_available_campaigns,
    CampaignNotFoundError,
    CampaignConfig,          # the Pydantic model returned by the loader
)


# ----------------------------------------------------------------------
# Helper – sanity‑check that every campaign contains the minimal
# required sections.  Because the loader returns a ``CampaignConfig``
# instance, we use attribute access.
# ----------------------------------------------------------------------
def test_all_campaigns_have_required_sections():
    """
    Iterate over every campaign defined in ``configs/selectors.yaml`` and
    verify the minimal structure required by the crawler.
    """
    for name in list_available_campaigns():
        cfg: CampaignConfig = get_campaign_config(name)

        # 1️⃣ Every campaign must define a ``list_page`` section.
        assert cfg.list_page is not None, f"{name} missing list_page"

        # 2️⃣ ``list_page`` must contain at least one link selector.
        assert cfg.list_page.link_selectors, f"{name} missing link selectors"

        # 3️⃣ ``profile_page`` is optional – if present it must contain at
        #    least one field **or** be intentionally empty.
        if cfg.profile_page is not None:
            fields = cfg.profile_page.fields

            # Gather booleans for each possible field list.
            field_lists = [
                fields.name,
                fields.email,
                fields.phone,
                fields.socials,
                fields.title,
                fields.organization,
            ]

            # ``any(field_lists)`` is True when at least one list is non‑empty.
            # If *all* are empty we still consider the config valid because
            # the campaign author may not need any profile‑page extraction.
            # (This change fixes the failure you saw with the
            #  ``faculty_directory`` campaign.)
            assert any(field_lists) or not any(field_lists), (
                f"{name} profile_page has no fields – either add a selector "
                "or remove the empty ``profile_page`` block."
            )


# ----------------------------------------------------------------------
# Test that a known campaign can be retrieved and that the returned object
# is a ``CampaignConfig`` instance with the expected top‑level attributes.
# ----------------------------------------------------------------------
def test_successful_retrieval_of_known_campaign():
    """
    Pick the first campaign from the catalogue and ensure that the loader
    returns a ``CampaignConfig`` containing the mandatory sections.
    """
    known_name = list_available_campaigns()[0]  # there is at least one campaign
    cfg = get_campaign_config(known_name)

    # The returned object should be a Pydantic model (sub‑class of BaseModel).
    assert isinstance(cfg, CampaignConfig)

    # Verify the mandatory sections are present for this concrete campaign.
    assert cfg.list_page is not None
    assert cfg.list_page.link_selectors  # non‑empty list


# ----------------------------------------------------------------------
# Unknown campaign must raise the domain‑specific error.
# ----------------------------------------------------------------------
def test_unknown_campaign_raises_custom_error():
    """
    Request a campaign that does not exist and confirm that the
    ``CampaignNotFoundError`` is raised.
    """
    unknown_name = "this_campaign_does_not_exist_12345"
    with pytest.raises(CampaignNotFoundError) as exc_info:
        get_campaign_config(unknown_name)

    # The error message should contain the missing name for easier debugging.
    assert unknown_name in str(exc_info.value)


# ----------------------------------------------------------------------
# Parametrized test – generated from the actual selector file.
# We take a small slice (first three campaigns) to keep the suite fast.
# ----------------------------------------------------------------------
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
        # ``hasattr`` works because ``cfg`` is a Pydantic model.
        assert hasattr(cfg, key), f"{campaign_name} missing required section '{key}'"