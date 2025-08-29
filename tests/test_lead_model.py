# tests/test_lead_model.py
import pytest
from models.lead import Lead

def test_happy_path():
    """All setters store the value and record the source URL."""
    l = Lead()
    l.set_name("Alice Example", "https://site.com/profile/alice")
    l.set_email("alice@example.com", "https://site.com/profile/alice")
    l.set_phone("+1‑555‑123‑4567", "https://site.com/contact")
    # Verify stored values
    assert l.name == "Alice Example"
    assert l.email == "alice@example.com"
    assert l.phone == "+1‑555‑123‑4567"
    # Verify provenance dict
    assert l.source_urls["name"] == ["https://site.com/profile/alice"]
    assert l.source_urls["email"] == ["https://site.com/profile/alice"]
    assert l.source_urls["phone"] == ["https://site.com/contact"]

def test_duplicate_url_not_added():
    """Calling a setter twice with the same URL should not duplicate it."""
    l = Lead()
    url = "https://example.com/profile"
    l.set_email("a@b.com", url)
    l.set_email("a@b.com", url)   # same URL again
    # Only one entry should exist
    assert l.source_urls["email"] == [url]

def test_missing_optional_fields_are_none():
    """Fields we never set stay as None and have no provenance entry."""
    l = Lead()
    assert l.name is None
    assert "name" not in l.source_urls