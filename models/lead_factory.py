# models/lead_factory.py
from __future__ import annotations

from typing import Mapping, Any

from .lead import Lead


def lead_from_mapping(data: Mapping[str, Any]) -> Lead:
    """
    Build a :class:`models.lead.Lead` from a generic ``dict``‑like object.

    The function:
    • Filters out keys that are not fields of ``Lead`` (so stray scraper data
      won’t raise a validation error).
    • Allows callers to pass either a plain ``dict`` or any mapping
      (e.g. ``pydantic.BaseModel.dict()``).

    Example
    -------
    >>> raw = {"first_name": "Ada", "email": "ada@example.com", "extra": 42}
    >>> lead = lead_from_mapping(raw)
    >>> lead.extra   # attribute does not exist → AttributeError
    >>> lead.email
    'ada@example.com'
    """
    # ``Lead.__fields__`` is a dict of field definitions provided by Pydantic
    allowed_keys = set(Lead.__fields__)
    filtered = {k: v for k, v in data.items() if k in allowed_keys}
    return Lead(**filtered)