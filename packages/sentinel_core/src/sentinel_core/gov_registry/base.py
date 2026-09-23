"""The government integration gateway — docs/01-ARCHITECTURE.md §6.4's
`ExternalRegistry` port: "On the day you grant access, this is a credential
change, not a project."

Every provider (VAHAN, SARTHI, eGujCop, AFIS) implements the same four
lookups; a provider that doesn't offer a given operation raises
`OperationNotSupportedError` rather than silently returning nothing, so a caller
looping over providers can tell "this registry doesn't do that" apart from
"this registry has no record for that query."
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from pydantic import BaseModel, Field

__all__ = [
    "AlertPushResult",
    "ExternalRegistry",
    "LicenceRecord",
    "OperationNotSupportedError",
    "PersonQuery",
    "PersonRecord",
    "RegistryAuditEvent",
    "RegistryError",
    "VehicleRecord",
]


class RegistryError(Exception):
    """Base for every ExternalRegistry failure mode — lets a caller catch
    'the government system said no' without also swallowing programming
    errors."""


class OperationNotSupportedError(RegistryError):
    """Raised when a provider is asked for a lookup outside its domain
    (e.g. VAHAN doesn't do licence lookups — that's SARTHI's job)."""


class RegistryUnavailableError(RegistryError):
    """Raised when the circuit breaker is open or the rate limit was
    exceeded — the caller should back off, not retry immediately."""


class VehicleRecord(BaseModel):
    """A VAHAN-style vehicle registration record. `owner_name`/`address`/
    `chassis_number`/`engine_number` are PII — see `audit_safe_dict()`."""

    plate: str
    owner_name: str
    vehicle_class: str
    make_model: str
    registration_date: str
    rc_status: str = Field(description="'active' / 'suspended' / 'blacklisted' / 'scrapped'")
    chassis_number: str
    engine_number: str
    address: str
    insurance_valid_until: str | None = None

    _pii_fields = ("owner_name", "chassis_number", "engine_number", "address")

    def audit_safe_dict(self) -> dict[str, object]:
        return _redact(self.model_dump(), self._pii_fields)


class LicenceRecord(BaseModel):
    """A SARTHI-style driving licence record."""

    dl_number: str
    holder_name: str
    date_of_birth: str
    licence_class: list[str]
    valid_until: str
    status: str = Field(description="'active' / 'suspended' / 'expired' / 'disqualified'")
    address: str
    endorsements: list[str] = Field(default_factory=list)

    _pii_fields = ("holder_name", "date_of_birth", "address")

    def audit_safe_dict(self) -> dict[str, object]:
        return _redact(self.model_dump(), self._pii_fields)


class PersonQuery(BaseModel):
    """A person lookup can be keyed by name+identifier (eGujCop's case
    records) or by a biometric reference (AFIS) — both providers accept
    this same shape and use whichever fields are relevant to them."""

    full_name: str | None = None
    identifier: str | None = Field(default=None, description="Aadhaar/voter ID/case party ID")
    photo_hash: str | None = Field(default=None, description="sha256 of a probe photo, for AFIS")


class PersonRecord(BaseModel):
    """A person-of-interest cross-reference — eGujCop's case/FIR records or
    AFIS's biometric identity match, depending on which provider answered."""

    person_id: str
    full_name: str
    match_confidence: float = Field(ge=0.0, le=1.0)
    flags: list[str] = Field(
        default_factory=list, description="e.g. 'active-FIR', 'wanted', 'history-sheeter'"
    )
    case_references: list[str] = Field(default_factory=list)
    source: str = Field(description="Which provider/system produced this record")

    _pii_fields = ("full_name",)

    def audit_safe_dict(self) -> dict[str, object]:
        return _redact(self.model_dump(), self._pii_fields)


class AlertPushResult(BaseModel):
    accepted: bool
    reference_id: str | None = None
    detail: str | None = None


class RegistryAuditEvent(BaseModel):
    """One field-level-audited call to an ExternalRegistry provider —
    docs/01-ARCHITECTURE.md §6.4's 'field-level audit and PII redaction
    rules'. Query parameters are logged in the clear (they're the lookup
    key an operator typed in, already visible to them); *results* are
    logged only in their `audit_safe_dict()` form."""

    provider_id: str
    operation: str
    query: dict[str, object]
    found: bool
    latency_ms: float
    requested_at: datetime
    actor: str | None = None
    detail: str | None = None


def _redact(data: dict[str, object], pii_fields: tuple[str, ...]) -> dict[str, object]:
    redacted = dict(data)
    for field_name in pii_fields:
        value = redacted.get(field_name)
        if isinstance(value, str) and value:
            redacted[field_name] = _mask(value)
    return redacted


def _mask(value: str) -> str:
    """Keep the first letter of each word, mask the rest — enough for an
    auditor to recognise a record without reading the PII itself."""
    return " ".join(f"{word[0]}{'*' * (len(word) - 1)}" if word else word for word in value.split())


class ExternalRegistry(Protocol):
    """docs/01-ARCHITECTURE.md §6.4's port. `provider_id` names which real
    government system this stands in for."""

    provider_id: str

    async def lookup_vehicle(self, plate: str) -> VehicleRecord | None: ...

    async def lookup_licence(self, dl_number: str) -> LicenceRecord | None: ...

    async def lookup_person(self, query: PersonQuery) -> list[PersonRecord]: ...

    async def push_alert(
        self, *, case_reference: str, summary: str, priority: str = "normal"
    ) -> AlertPushResult: ...
