"""AFIS provider — a contract-shaped mock for a state Automated Fingerprint
Identification System, generalised here to biometric identity matching
(a `photo_hash` probe rather than a fingerprint minutia scan, since this
platform's own capture is camera-based, not a fingerprint scanner). Same
`PersonQuery`/`PersonRecord` shape as eGujCop, but AFIS answers from a
biometric gallery rather than case records — a different real dataset with
the same lookup contract.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Sequence
from datetime import UTC, datetime

import httpx

from sentinel_core.gov_registry.base import (
    AlertPushResult,
    LicenceRecord,
    OperationNotSupportedError,
    PersonQuery,
    PersonRecord,
    RegistryAuditEvent,
    VehicleRecord,
    reject_auth_failure,
)
from sentinel_core.gov_registry.resilience import CircuitBreaker, RateLimiter, with_retry

__all__ = ["AfisProvider", "NafisProvider"]

logger = logging.getLogger(__name__)

_MOCK_GALLERY: dict[str, dict[str, object]] = {
    "sha256:af1s0001": {
        "person_id": "AFIS-GJ-0041872",
        "full_name": "Suresh Chauhan",
        "flags": ["wanted"],
        "case_references": ["FIR/2023/GJ27/00812"],
        "source": "afis",
    },
    "sha256:af1s0002": {
        "person_id": "AFIS-GJ-0018903",
        "full_name": "Kiran Desai",
        "flags": ["missing-person"],
        "case_references": ["MP/2022/GJ01/00033"],
        "source": "afis",
    },
}


# NAFIS (NCRB's National Automated Fingerprint Identification System) holds
# records from every state, keyed by a National Fingerprint Number. A probe
# that misses the state AFIS can still hit an offender booked elsewhere.
_NAFIS_MOCK_GALLERY: dict[str, dict[str, object]] = {
    "sha256:af1s0001": {
        "person_id": "NFN-24-0000417726",
        "full_name": "Suresh Chauhan",
        "flags": ["wanted"],
        "case_references": ["FIR/2023/GJ27/00812"],
        "source": "nafis",
    },
    "sha256:nf150003": {
        "person_id": "NFN-23-0001093381",
        "full_name": "Rakesh Yadav",
        "flags": ["wanted", "inter-state"],
        "case_references": ["FIR/2021/MH12/04417"],
        "source": "nafis",
    },
}


def _default_transport(gallery: dict[str, dict[str, object]], api_key: str) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.headers.get("x-api-key") != api_key:
            return httpx.Response(401, json={"error": "invalid api key"})
        photo_hash = request.url.params.get("photo_hash", "")
        record = gallery.get(photo_hash)
        matches = [{**record, "match_confidence": 0.88}] if record else []
        return httpx.Response(200, json={"matches": matches})

    return httpx.MockTransport(handler)


class AfisProvider:
    """Biometric person lookups only — a photo_hash-less query (name-only,
    identifier-only) can't be answered by a biometric gallery, so it
    simply returns no matches rather than raising, since that's a valid
    (if unhelpful) query shape for this Protocol's shared `PersonQuery`."""

    provider_id = "afis"
    display_name = "AFIS"
    default_base_url = "https://afis.gujaratpolice.gov.in"
    mock_api_key = "mock-afis-key"
    mock_gallery = _MOCK_GALLERY

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout_s: float = 5.0,
        transport: httpx.AsyncBaseTransport | None = None,
        circuit_breaker: CircuitBreaker | None = None,
        rate_limiter: RateLimiter | None = None,
    ):
        self._base_url = base_url or self.default_base_url
        self._api_key = api_key or self.mock_api_key
        self._timeout_s = timeout_s
        self._transport = transport or _default_transport(self.mock_gallery, self.mock_api_key)
        self._circuit_breaker = circuit_breaker or CircuitBreaker()
        self._rate_limiter = rate_limiter or RateLimiter(capacity=30, refill_period_s=60.0)

    async def lookup_vehicle(self, plate: str) -> VehicleRecord | None:
        raise OperationNotSupportedError(f"{self.display_name} does not provide vehicle lookups")

    async def lookup_licence(self, dl_number: str) -> LicenceRecord | None:
        raise OperationNotSupportedError(f"{self.display_name} does not provide licence lookups")

    async def lookup_person(self, query: PersonQuery) -> list[PersonRecord]:
        self._rate_limiter.acquire()
        started = time.monotonic()

        if not query.photo_hash:
            self._audit("lookup_person", {}, [], time.monotonic() - started)
            return []

        async def _call() -> httpx.Response:
            async with httpx.AsyncClient(
                base_url=self._base_url, timeout=self._timeout_s, transport=self._transport
            ) as client:
                return await client.get(
                    "/api/v1/identify",
                    params={"photo_hash": query.photo_hash or ""},
                    headers={"x-api-key": self._api_key},
                )

        resp = await with_retry(_call, circuit_breaker=self._circuit_breaker)

        reject_auth_failure(resp.status_code, self.provider_id)
        records = [PersonRecord(**m) for m in resp.json().get("matches", [])]
        self._audit(
            "lookup_person", {"photo_hash": query.photo_hash}, records, time.monotonic() - started
        )
        return records

    async def push_alert(
        self, *, case_reference: str, summary: str, priority: str = "normal"
    ) -> AlertPushResult:
        raise OperationNotSupportedError(f"{self.display_name} does not accept pushed alerts")

    def _audit(
        self,
        operation: str,
        query: dict[str, object],
        records: Sequence[object],
        elapsed_s: float,
    ) -> None:
        event = RegistryAuditEvent(
            provider_id=self.provider_id,
            operation=operation,
            query=query,
            found=bool(records),
            latency_ms=elapsed_s * 1000,
            requested_at=datetime.now(UTC),
        )
        logger.info("gov_registry_audit", extra={"audit_event": event.model_dump(mode="json")})


class NafisProvider(AfisProvider):
    """NCRB's national fingerprint system: the same identify contract as the
    state AFIS, answered from the national gallery. Queried after the state
    AFIS so an offender with no Gujarat record is still found."""

    provider_id = "nafis"
    display_name = "NAFIS"
    default_base_url = "https://nafis.ncrb.gov.in"
    mock_api_key = "mock-nafis-key"
    mock_gallery = _NAFIS_MOCK_GALLERY
