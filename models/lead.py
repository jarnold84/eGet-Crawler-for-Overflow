# models/lead.py
from __future__ import annotations

from typing import List, Dict, Optional, Union

from pydantic import BaseModel, Field, field_validator


class Lead(BaseModel):
    """
    Pydantic v2 representation of a scraped lead.
    Mirrors the OUS‑3‑SS JSON schema and records per‑field provenance.
    """

    # --------------------------------------------------------------------- #
    # Core identifiers
    # --------------------------------------------------------------------- #
    name: Optional[str] = None
    business_name: Optional[str] = None
    profile_link: Optional[str] = None

    # --------------------------------------------------------------------- #
    # Contact channels
    # --------------------------------------------------------------------- #
    email: Optional[str] = None
    phone: Optional[str] = None
    social_handles: Optional[Dict[str, str]] = None  # e.g. {"instagram": "..."} 

    # --------------------------------------------------------------------- #
    # Contextual / descriptive fields
    # --------------------------------------------------------------------- #
    services_offered: Optional[List[str]] = None
    style_vibe_descriptors: Optional[List[str]] = None
    location: Optional[Union[str, Dict]] = None
    team_member_names: Optional[List[str]] = None
    portfolio_links: Optional[List[str]] = None
    booking_contact_links: Optional[List[str]] = None
    testimonials_social_proof: Optional[
        List[Union[str, Dict[str, str]]]
    ] = None
    values_mission_statement: Optional[str] = None

    # --------------------------------------------------------------------- #
    # Raw page artefacts & scoring
    # --------------------------------------------------------------------- #
    raw_page_text: Optional[str] = None
    confidence: Optional[float] = None
    flags: Optional[List[str]] = None

    # --------------------------------------------------------------------- #
    # Provenance – every non‑empty field must list the URL(s) that produced it
    # --------------------------------------------------------------------- #
    source_urls: Optional[
        Dict[
            str,
            Union[
                List[str],                     # simple field → list of URLs
                Dict[str, List[str]],          # nested socials → platform → URLs
            ],
        ]
    ] = None

    # --------------------------------------------------------------------- #
    # Internal helpers (not part of the exported schema)
    # --------------------------------------------------------------------- #
    class Config:
        # Allow arbitrary extra keys if a future field slips in; they’ll be ignored.
        extra = "ignore"

    # --------------------------------------------------------------------- #
    # Utility methods
    # --------------------------------------------------------------------- #
    def _ensure_source_dict(self) -> Dict:
        """Create ``source_urls`` if it does not exist and return it."""
        if self.source_urls is None:
            self.source_urls = {}
        return self.source_urls

    def is_three_source_valid(self) -> bool:
        """
        Returns True if at least two distinct contact channels are present
        among email, phone, and any non‑empty social handle.
        """
        channels = sum(bool(x) for x in (self.email, self.phone, self.social_handles))
        # ``social_handles`` counts as a channel only if it contains a value
        if self.social_handles:
            channels -= 1  # we counted it already; now verify it isn’t empty
            if any(v for v in self.social_handles.values()):
                channels += 1
        return channels >= 2

    # --------------------------------------------------------------------- #
    # Setter methods – each updates the field **and** its provenance entry
    # --------------------------------------------------------------------- #
    # Basic identifiers ----------------------------------------------------
    def set_name(self, name: str, source_url: str) -> None:
        self.name = name
        self._ensure_source_dict()["name"] = [source_url]

    def set_business_name(self, business_name: str, source_url: str) -> None:
        self.business_name = business_name
        self._ensure_source_dict()["businessName"] = [source_url]

    def set_profile_link(self, url: str) -> None:
        self.profile_link = url
        self._ensure_source_dict()["profileLink"] = [url]

    # Contact channels ------------------------------------------------------
    def set_email(self, email: str, source_url: str) -> None:
        self.email = email
        self._ensure_source_dict()["email"] = [source_url]

    def set_phone(self, phone: str, source_url: str) -> None:
        self.phone = phone
        self._ensure_source_dict()["phone"] = [source_url]

    def set_social_handles(
        self, handles: Dict[str, str], source_url: str
    ) -> None:
        """
        ``handles`` maps platform → URL (e.g. {"instagram": "https://…"}).
        """
        self.social_handles = handles
        src = self._ensure_source_dict()
        src.setdefault("socialHandles", {})
        for platform in handles:
            src["socialHandles"].setdefault(platform, []).append(source_url)

    # Contextual fields -----------------------------------------------------
    def _list_setter(
        self,
        attr_name: str,
        values: List[str],
        source_url: str,
        src_key: Optional[str] = None,
    ) -> None:
        """Generic helper for list‑type fields that also records provenance."""
        setattr(self, attr_name, values)
        src = self._ensure_source_dict()
        key = src_key or attr_name
        src[key] = [source_url]

    def set_services_offered(
        self, services: List[str], source_url: str
    ) -> None:
        self._list_setter(
            "services_offered",
            services,
            source_url,
            src_key="servicesOffered",
        )

    def set_style_vibe_descriptors(
        self, descriptors: List[str], source_url: str
    ) -> None:
        self._list_setter(
            "style_vibe_descriptors",
            descriptors,
            source_url,
            src_key="styleVibeDescriptors",
        )

    def set_location(self, location: Union[str, Dict], source_url: str) -> None:
        self.location = location
        self._ensure_source_dict()["location"] = [source_url]

    def set_team_member_names(
        self, names: List[str], source_url: str
    ) -> None:
        self._list_setter(
            "team_member_names", names, source_url, src_key="teamMemberNames"
        )

    def set_portfolio_links(
        self, links: List[str], source_url: str
    ) -> None:
        self._list_setter(
            "portfolio_links", links, source_url, src_key="portfolioLinks"
        )

    def set_booking_contact_links(
        self, links: List[str], source_url: str
    ) -> None:
        self._list_setter(
            "booking_contact_links",
            links,
            source_url,
            src_key="bookingContactLinks",
        )

    def set_testimonials_social_proof(
        self,
        testimonials: List[Union[str, Dict[str, str]]],
        source_url: str,
    ) -> None:
        self.testimonials_social_proof = testimonials
        self._ensure_source_dict()["testimonialsSocialProof"] = [source_url]

    def set_values_mission_statement(
        self, statement: str, source_url: str
    ) -> None:
        self.values_mission_statement = statement
        self._ensure_source_dict()["valuesMissionStatement"] = [source_url]

    # Raw page & scoring ----------------------------------------------------
    def set_raw_page_text(self, text: str, source_url: str) -> None:
        self.raw_page_text = text
        self._ensure_source_dict()["rawPageText"] = [source_url]

    def set_confidence(self, confidence: float) -> None:
        self.confidence = confidence

    def add_flag(self, flag: str) -> None:
        """Append a QA / processing flag (e.g. LOW_CONFIDENCE)."""
        if self.flags is None:
            self.flags = []
        if flag not in self.flags:
            self.flags.append(flag)

    # --------------------------------------------------------------------- #
    # Export helpers
    # --------------------------------------------------------------------- #
    def to_dict(self) -> Dict:
        """
        Serialise the lead to a plain dict ready for JSON export or
        Google‑Sheets insertion. ``exclude_none=True`` drops empty fields,
        keeping the payload tidy.
        """
        return self.model_dump(exclude_none=True)

    # --------------------------------------------------------------------- #
    # Field validators (Pydantic v2 style)
    # --------------------------------------------------------------------- #
    @field_validator("email")
    @classmethod
    def _validate_email(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError(f"Invalid email format: {v}")
        return v

    @field_validator("phone")
    @classmethod
    def _validate_phone(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        # Very permissive – keep digits, plus, hyphen, space
        cleaned = "".join(ch for ch in v if ch.isdigit() or ch in "+- ")
        if len(cleaned) < 7:
            raise ValueError(f"Phone number looks too short: {v}")
        return cleaned