# ────────────────────────────────────────────────────────────────
# tests/test_lead_additional.py
# ────────────────────────────────────────────────────────────────
import pytest
from pydantic import ValidationError
from models.lead import Lead


# -------------------------------------------------------------------
# 1️⃣  is_three_source_valid – email / phone / social_handles logic
# -------------------------------------------------------------------
def test_is_three_source_valid_two_channels():
    """
    The helper returns True when **any two** of the three possible
    contact channels are present (email, phone, or a non‑empty
    ``social_handles`` dict).  We exercise the simplest case:
    email + phone.
    """
    lead = Lead(email="alice@example.com", phone="+1 555‑1234")
    assert lead.is_three_source_valid() is True


def test_is_three_source_valid_one_channel():
    """
    With only a single channel (here a non‑empty ``social_handles``)
    the helper must return False.
    """
    lead = Lead(social_handles={"twitter": "https://t.co/xyz"})
    assert lead.is_three_source_valid() is False


def test_is_three_source_valid_no_channels():
    """
    Completely empty contact information → False.
    """
    lead = Lead()
    assert lead.is_three_source_valid() is False


# -------------------------------------------------------------------
# 2️⃣  source_urls – type expectations (list of strings)
# -------------------------------------------------------------------
def test_source_urls_accepts_lists():
    """
    ``source_urls`` is declared as ``Dict[str, Union[List[str], Dict[str,
    List[str]]]``.  Supplying a list for each key therefore validates
    correctly and the values are preserved unchanged.
    """
    lead = Lead(
        source_urls={
            "url":  ["https://example.com"],
            "file": ["file.txt"],
            "text": ["some text"],
        }
    )
    # The model should store exactly what we gave it.
    assert lead.source_urls == {
        "url":  ["https://example.com"],
        "file": ["file.txt"],
        "text": ["some text"],
    }


def test_invalid_source_urls_type_raises():
    """
    Passing a plain string (instead of a list) violates the type
    constraint and raises a ``ValidationError``.
    """
    with pytest.raises(ValidationError):
        Lead(source_urls={"url": "https://example.com"})  # <-- should be a list


# -------------------------------------------------------------------
# 3️⃣  Setters automatically record provenance in source_urls
# -------------------------------------------------------------------
def test_setters_populate_source_urls():
    """
    Using the public setters (`set_email`, `set_phone`,
    `set_social_handles`) must add entries to ``source_urls`` with the
    supplied source URL.
    """
    lead = Lead()
    lead.set_email("bob@example.com", src_url="https://src.email")
    lead.set_phone("+1 555‑9999", src_url="https://src.phone")
    lead.set_social_handles({"linkedin": "https://lnkd.in/abc"}, src_url="https://src.social")

    # Verify the three provenance lists were created.
    assert lead.source_urls["email"] == ["https://src.email"]
    assert lead.source_urls["phone"] == ["https://src.phone"]
    # ``socialHandles`` is a nested dict → platform → list of URLs
    assert lead.source_urls["socialHandles"]["linkedin"] == ["https://src.social"]


# -------------------------------------------------------------------
# 4️⃣  to_dict always includes source_urls (when present)
# -------------------------------------------------------------------
def test_to_dict_includes_source_urls_when_set():
    """
    ``Lead.to_dict()`` serialises the model with ``exclude_none=True``.
    When we have populated ``source_urls`` via a setter, the resulting
    dict must contain that top‑level key and preserve the list values.
    """
    lead = Lead()
    lead.set_email("carol@example.com", src_url="https://src.email")
    exported = lead.to_dict()

    assert "source_urls" in exported
    # The inner mapping should hold the list we added.
    assert exported["source_urls"]["email"] == ["https://src.email"]