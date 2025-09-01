# services/models/lead.py
from __future__ import annotations

from typing import List, Dict, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Lead(BaseModel):
    """
    Pydantic v2 model for a single prospect.
    Every mutable field has a corresponding entry in ``source_urls`` that
    records the URL(s) that supplied the value.
    """

    # ------------------------------------------------------------------
    # Core identifiers (canonical names)
    # ------------------------------------------------------------------
    name: Optional[str] = None
    business_name: Optional[str] = None          # <- underlying storage for title / organization
    profile_link: Optional[str] = None

    # ------------------------------------------------------------------
    # Contact channels (canonical names)
    # ------------------------------------------------------------------
    email: Optional[str] = None
    phone: Optional[str] = None
    social_handles: Optional[Dict[str, str]] = None   # platform → URL (canonical)

    # ------------------------------------------------------------------
    # Context / descriptive fields
    # ------------------------------------------------------------------
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

    # ------------------------------------------------------------------
    # Raw artefacts & scoring
    # ------------------------------------------------------------------
    raw_page_text: Optional[str] = None
    confidence: Optional[float] = None
    flags: Optional[List[str]] = None

    # ------------------------------------------------------------------
    # Provenance – every non‑empty field records the URL(s) that produced it
    # ------------------------------------------------------------------
    source_urls: Dict[
        str,
        Union[
            List[str],                     # simple field → list of URLs
            Dict[str, List[str]],          # nested socials → platform → URLs
        ],
    ] = Field(default_factory=dict)

    # ------------------------------------------------------------------
    # Pydantic configuration – allow population by alias name and ignore extras
    # ------------------------------------------------------------------
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    # ------------------------------------------------------------------
    # Alias fields required by the scraper (title, organization, socials)
    # ------------------------------------------------------------------
    # These are *properties* that proxy to the canonical attributes.
    # They behave like regular fields for the scraper while keeping a single
    # source of truth internally.

    @property
    def title(self) -> Optional[str]:
        """Alias for ``business_name``."""
        return self.business_name

    @title.setter
    def title(self, value: Optional[str]) -> None:
        self.business_name = value

    @property
    def organization(self) -> Optional[str]:
        """Another alias for ``business_name``."""
        return self.business_name

    @organization.setter
    def organization(self, value: Optional[str]) -> None:
        self.business_name = value

    @property
    def socials(self) -> Optional[Dict[str, str]]:
        """Alias for ``social_handles``."""
        return self.social_handles

    @socials.setter
    def socials(self, value: Optional[Dict[str, str]]) -> None:
        self.social_handles = value

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _add_source(self, field: str, url: str) -> None:
        """
        Append *url* to the provenance list for *field*,
        creating the list if it does not exist.
        Duplicate URLs are ignored.
        """
        src = self.source_urls
        if field not in src:
            src[field] = []                     # type: ignore[assignment]
        # ``src[field]`` is either List[str] or Dict[str, List[str]];
        # callers guarantee they pass a plain field name here.
        if url not in src[field]:               # type: ignore[index]
            src[field].append(url)               # type: ignore[call-arg]

    # ------------------------------------------------------------------
    # Generic whitespace / empty‑string normaliser
    # ------------------------------------------------------------------
    @field_validator("*", mode="before")
    @classmethod
    def _strip_and_nullify(
        cls,
        v: Optional[Union[str, List, Dict]],
    ) -> Optional[Union[str, List, Dict]]:
        """
        * Strip leading/trailing whitespace from strings.
        * Convert empty strings (after stripping) to ``None``.
        * Leave non‑string values untouched.
        """
        if isinstance(v, str):
            v = v.strip()
            return v or None
        return v

    # ------------------------------------------------------------------
    # Email & phone validators (run on model creation – also used in setters)
    # ------------------------------------------------------------------
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
        """
        Very permissive phone validation:
        * keep digits, plus, hyphen, space
        * reject only if nothing useful remains (e.g. an empty string)
        * do **not** enforce a minimum length – the model only needs a
          non‑empty value to count as a contact channel.
        """
        if v is None:
            return v

        cleaned = "".join(ch for ch in v if ch.isdigit() or ch in "+- ")
        # If cleaning stripped everything, the input wasn’t a phone number.
        if not cleaned:
            raise ValueError(f"Phone number looks invalid: {v}")

        return cleaned

    # ------------------------------------------------------------------
    # Public setters – each writes the value **and** records provenance
    # ------------------------------------------------------------------
    # Core identifiers ----------------------------------------------------
    def set_name(self, value: str, src_url: str) -> None:
        # Apply the same whitespace‑normalisation the validator does
        value = value.strip() or None
        self.name = value
        if value is not None:
            self._add_source("name", src_url)

    def set_business_name(self, business_name: str, src_url: str) -> None:
        business_name = business_name.strip() or None
        self.business_name = business_name
        if business_name is not None:
            self._add_source("businessName", src_url)

    def set_profile_link(self, url: str) -> None:
        self.profile_link = url
        self._add_source("profileLink", url)

    # Contact channels ------------------------------------------------------
    def set_email(self, email: str, src_url: str) -> None:
        # Normalise whitespace first
        email = email.strip() or None
        # Run the same validation we defined for the model
        if email is not None:
            # This will raise ValueError if the format is wrong
            self.__class__._validate_email(email)
        self.email = email
        if email is not None:
            self._add_source("email", src_url)

    def set_phone(self, phone: str, src_url: str) -> None:
        phone = phone.strip() or None
        if phone is not None:
            self.__class__._validate_phone(phone)
        self.phone = phone
        if phone is not None:
            self._add_source("phone", src_url)

    def set_social_handles(
        self, handles: Dict[str, str], src_url: str
    ) -> None:
        """
        ``handles`` maps platform → URL (e.g. {"instagram": "https://…"}).
        Provenance is stored per‑platform under ``source_urls["socialHandles"]``.
        """
        self.social_handles = handles
        src = self.source_urls
        src.setdefault("socialHandles", {})  # type: ignore[assignment]
        for platform in handles:
            src["socialHandles"].setdefault(platform, [])  # type: ignore[index]
            if src_url not in src["socialHandles"][platform]:  # type: ignore[index]
                src["socialHandles"][platform].append(src_url)  # type: ignore[index]

    # Helper for list‑type fields -------------------------------------------
    def _list_setter(
        self,
        attr_name: str,
        values: List[str],
        src_url: str,
        src_key: Optional[str] = None,
    ) -> None:
        setattr(self, attr_name, values)
        key = src_key or attr_name
        self._add_source(key, src_url)

    # Contextual fields -----------------------------------------------------
    def set_services_offered(
        self, services: List[str], src_url: str
    ) -> None:
        self._list_setter(
            "services_offered",
            services,
            src_url,
            src_key="servicesOffered",
        )

    def set_style_vibe_descriptors(
        self, descriptors: List[str], src_url: str
    ) -> None:
        self._list_setter(
            "style_vibe_descriptors",
            descriptors,
            src_url,
            src_key="styleVibeDescriptors",
        )

    def set_location(self, location: Union[str, Dict], src_url: str) -> None:
        self.location = location
        self._add_source("location", src_url)

    def set_team_member_names(
        self, names: List[str], src_url: str
    ) -> None:
        self._list_setter(
            "team_member_names", names, src_url, src_key="teamMemberNames"
        )

    def set_portfolio_links(
        self, links: List[str], src_url: str
    ) -> None:
        self._list_setter(
            "portfolio_links", links, src_url, src_key="portfolioLinks"
        )

    def set_booking_contact_links(
        self, links: List[str], src_url: str
    ) -> None:
        self._list_setter(
            "booking_contact_links",
            links,
            src_url,
            src_key="bookingContactLinks",
        )

    def set_testimonials_social_proof(
        self,
        testimonials: List[Union[str, Dict[str, str]]],
        src_url: str,
    ) -> None:
        self.testimonials_social_proof = testimonials
        self._add_source("testimonialsSocialProof", src_url)

    def set_values_mission_statement(
        self, statement: str, src_url: str
    ) -> None:
        self.values_mission_statement = statement
        self._add_source("valuesMissionStatement", src_url)

    # Raw page & scoring ----------------------------------------------------
    def set_raw_page_text(self, text: str, src_url: str) -> None:
        self.raw_page_text = text
        self._add_source("rawPageText", src_url)

    def set_confidence(self, confidence: float) -> None:
        self.confidence = confidence

    def add_flag(self, flag: str) -> None:
        """Append a QA / processing flag (e.g. LOW_CONFIDENCE)."""
        if self.flags is None:
            self.flags = []
        if flag not in self.flags:
            self.flags.append(flag)

    # ------------------------------------------------------------------
    # Export helpers
    # ------------------------------------------------------------------
    def to_dict(self) -> Dict:
        """
        Serialise the lead to a plain dict ready for JSON export or
        Google‑Sheets insertion. ``exclude_none=True`` drops empty fields,
        keeping the payload tidy.
        """
        return self.model_dump(exclude_none=True)

    # ------------------------------------------------------------------
    # Contact‑channel helper
    # ------------------------------------------------------------------
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