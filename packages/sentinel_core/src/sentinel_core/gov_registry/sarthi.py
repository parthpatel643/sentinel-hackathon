"""SARTHI provider — a contract-shaped mock for India's driving-licence
registry. Same architecture as VahanProvider (see that module's docstring
for the "credential change, not a project" rationale) — deliberately not
sharing a base class with it beyond the `ExternalRegistry` Protocol,
since each real government system's request/response shape genuinely
differs and duplicating the small amount of plumbing keeps every provider
readable standalone.
"""

from __future__ import annotations

import logging
import time
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
)
from sentinel_core.gov_registry.resilience import CircuitBreaker, RateLimiter, with_retry

__all__ = ["SarthiProvider"]

logger = logging.getLogger(__name__)

_MOCK_LICENCES: dict[str, dict[str, object]] = {
    "GJ0120190001234": {
        "dl_number": "GJ0120190001234",
        "holder_name": "Ravi Patel",
        "date_of_birth": "1992-04-11",
        "licence_class": ["LMV", "MCWG"],
        "valid_until": "2039-04-10",
        "status": "active",
        "address": "14 Ellisbridge, Ahmedabad, Gujarat",
        "endorsements": [],
    },
    "GJ0520210005678": {
        "dl_number": "GJ0520210005678",
        "holder_name": "Meera Shah",
        "date_of_birth": "1998-09-23",
        "licence_class": ["MCWG"],
        "valid_until": "2041-09-22",
        "status": "active",
        "address": "Race Course Road, Vadodara, Gujarat",
        "endorsements": [],
    },
    "GJ2720150009012": {
        "dl_number": "GJ2720150009012",
        "holder_name": "Suresh Chauhan",
        "date_of_birth": "1980-01-05",
        "licence_class": ["HGV", "LMV"],
        "valid_until": "2035-01-04",
        "status": "disqualified",
        "address": "GIDC Industrial Estate, Surat, Gujarat",
        "endorsements": ["rash-driving-2022", "disqualified-6-months-2024"],
    },
}


def _default_transport() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.headers.get("x-api-key") != "mock-sarthi-key":
            return httpx.Response(401, json={"error": "invalid api key"})
        dl_number = request.url.params.get("dl_number", "")
        record = _MOCK_LICENCES.get(dl_number.upper())
        if record is None:
            return httpx.Response(404, json={"error": "not found"})
        return httpx.Response(200, json=record)

    return httpx.MockTransport(handler)


class SarthiProvider:
    """Licence lookups only."""

    provider_id = "sarthi"

    def __init__(
        self,
        *,
        base_url: str = "https://sarathi.parivahan.gov.in",
        api_key: str = "mock-sarthi-key",
        timeout_s: float = 5.0,
        transport: httpx.AsyncBaseTransport | None = None,
        circuit_breaker: CircuitBreaker | None = None,
        rate_limiter: RateLimiter | None = None,
    ):
        self._base_url = base_url
        self._api_key = api_key
        self._timeout_s = timeout_s
        self._transport = transport or _default_transport()
        self._circuit_breaker = circuit_breaker or CircuitBreaker()
        self._rate_limiter = rate_limiter or RateLimiter(capacity=60, refill_period_s=60.0)

    async def lookup_vehicle(self, plate: str) -> VehicleRecord | None:
        raise OperationNotSupportedError(
            "SARTHI does not provide vehicle lookups — see VahanProvider"
        )

    async def lookup_licence(self, dl_number: str) -> LicenceRecord | None:
        self._rate_limiter.acquire()
        started = time.monotonic()

        async def _call() -> httpx.Response:
            async with httpx.AsyncClient(
                base_url=self._base_url, timeout=self._timeout_s, transport=self._transport
            ) as client:
                return await client.get(
                    "/api/v1/licence",
                    params={"dl_number": dl_number.upper()},
                    headers={"x-api-key": self._api_key},
                )

        resp = await with_retry(_call, circuit_breaker=self._circuit_breaker)
        record = LicenceRecord(**resp.json()) if resp.status_code == 200 else None
        self._audit("lookup_licence", {"dl_number": dl_number}, record, time.monotonic() - started)
        return record

    async def lookup_person(self, query: PersonQuery) -> list[PersonRecord]:
        raise OperationNotSupportedError("SARTHI does not provide person lookups")

    async def push_alert(
        self, *, case_reference: str, summary: str, priority: str = "normal"
    ) -> AlertPushResult:
        raise OperationNotSupportedError("SARTHI does not accept pushed alerts")

    def _audit(
        self, operation: str, query: dict[str, object], record: object, elapsed_s: float
    ) -> None:
        event = RegistryAuditEvent(
            provider_id=self.provider_id,
            operation=operation,
            query=query,
            found=record is not None,
            latency_ms=elapsed_s * 1000,
            requested_at=datetime.now(UTC),
        )
        logger.info("gov_registry_audit", extra={"audit_event": event.model_dump(mode="json")})
