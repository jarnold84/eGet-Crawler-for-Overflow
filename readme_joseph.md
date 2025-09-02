README – Adding a New Campaign
📦 Overview
A campaign defines the selectors that the crawler uses to locate list‑pages, pagination links, and profile fields.
All campaigns live in configs/selectors.yaml and are loaded at runtime by services/crawler/config_loader.py.

Below is a step‑by‑step guide for contributors who need to add a brand‑new campaign (or modify an existing one) and verify that everything works.

1️⃣ Add the campaign to configs/selectors.yaml
Open configs/selectors.yaml.
Locate the top‑level selectors: mapping.
Insert a new key whose name is the campaign identifier you want to expose (e.g., my_new_site).
Under that key, provide the required structure:
selectors:
  my_new_site:                     # <-- campaign identifier
    list_page:
      link_selectors:
        - css: "a.profile-link"    # example – adapt to the target site
      pagination:
        next_css: ".next-page"     # optional – CSS selector for “next” button
        # next_xpath: "//a[@rel='next']"   # optional – XPath alternative
        # next_url_regex: "page=\\d+"     # optional – regex fallback
    profile_page:
      fields:
        name:
          - css: "h1.name"
        email:
          - xpath: "//a[contains(@href,'mailto:')]"
        phone:
          - css: ".contact .phone"
        socials:
          - css: ".socials a"
        title:
          - css: ".headline"
        organization:
          - css: ".company"
Tips
Keep the schema consistent – the keys (list_page, profile_page, fields, etc.) must match the TypedDict definitions in config_loader.py.
Prefer CSS selectors; use XPath only when CSS cannot express the rule.
Optional pagination fields (next_css, next_xpath, next_url_regex) can be omitted if the site has no pagination.
Test the selectors manually (e.g., with Chrome DevTools) before committing.
2️⃣ Update services/crawler/config_loader.py (only if you need custom logic)
In most cases no code change is required – the loader reads the entire selectors mapping and returns the sub‑dictionary for the requested campaign.

However, if you need to:

Pre‑process a selector (e.g., compile a regex ahead of time), or
Expose a derived alias (e.g., map legacy_name → my_new_site),
then edit config_loader.py:

def _load_yaml() -> dict:
    """Read the YAML file and return the inner ``selectors`` mapping."""
    with CONFIG_PATH.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
        return raw.get("selectors", {})

# Example of a simple alias mapping (optional)
_ALIAS_MAP = {
    "legacy_name": "my_new_site",
}

def get_campaign_config(campaign_name: str) -> CampaignConfig:
    # Resolve aliases first
    canonical_name = _ALIAS_MAP.get(campaign_name, campaign_name)
    raw_cfg = _load_yaml()
    try:
        return raw_cfg[canonical_name]  # type: ignore[return-value]
    except KeyError as exc:
        raise CampaignNotFoundError(canonical_name) from exc
If you don’t need any of the above, leave the file untouched.

3️⃣ Run the test suite to verify the new campaign
Activate your virtual environment (or create one):

python -m venv .venv
source .venv/bin/activate   # Linux/macOS
.venv\Scripts\activate      # Windows
Install the project in editable mode (ensures the latest code is used):

pip install -e .
Run the tests:

pytest -q
You should see something like:

..                                                                   [100%]
2 passed in 0.42s
If you added a new campaign, consider adding a small unit test (e.g., in tests/test_config_loader.py) that asserts:

from services.crawler.config_loader import get_campaign_config, CampaignNotFoundError

def test_my_new_site_is_loadable():
    cfg = get_campaign_config("my_new_site")
    assert "list_page" in cfg
    assert "profile_page" in cfg
Then re‑run pytest to confirm the test passes.

Check the CI (GitHub Actions).
Push your branch; the workflow will automatically:

Install dependencies
Run pip install -e .
Validate selectors.yaml (via the built‑in CI step)
Execute the test suite
All steps should end with a green checkmark.

📚 Recap – Quick Checklist
 Add a new key under selectors: in configs/selectors.yaml.
 Ensure the selector structure matches the TypedDict schema.
 (Optional) Update config_loader.py only if you need aliasing or preprocessing.
 Run pytest locally to confirm the new campaign loads without errors.
 Push the changes and verify the CI passes.
🙋‍♀️ Need help?
If anything feels unclear, open an issue or drop a comment on the PR.
Happy crawling! 🚀


Testing
The test suite now includes comprehensive checks for the Lead model. New tests verify the contact‑channel validation logic (is_three_source_valid), ensure provenance tracking via source_urls works correctly, and confirm proper serialization with to_dict. The updated file tests/test_lead_additional.py replaces the older version and brings the total test count to seven passing tests (7 passed).

Content extraction strategy 
The main scraper (services/scraper/scraper.py) contains a full‑featured ContentExtractor that performs HTML cleaning, metadata extraction, main‑article heuristics, and markdown conversion. A lightweight placeholder lives in services/crawler/content_extractor.py for rapid prototyping or future replacement. The placeholder is not used by the current production code.