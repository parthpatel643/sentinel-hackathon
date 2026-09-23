"""VAHAN provider — a contract-shaped mock for India's national vehicle
registration registry. docs/01-ARCHITECTURE.md §6.4: "each shipped with a
conformant mock driven by a representative dataset we create."

Structured exactly like a real HTTP integration would be (base URL, API
key header, injectable transport) even though there is no real VAHAN
credential to point at — swap `transport=None` (falls back to the built-in
mock) for a real `httpx.AsyncHTTPTransport` and a real `base_url`/`api_key`
and nothing else in this file needs to change. That's the "credential
change, not a project" promise made concrete.
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

__all__ = ["VahanProvider"]

logger = logging.getLogger(__name__)

# The representative dataset this mock is "driven by" — plausible Gujarat
# registrations, not real vehicle records.
_MOCK_VEHICLES: dict[str, dict[str, object]] = {
    "GJ01AB1234": {
        "plate": "GJ01AB1234",
        "owner_name": "Ravi Patel",
        "vehicle_class": "LMV",
        "make_model": "Maruti Suzuki Swift",
        "registration_date": "2019-06-14",
        "rc_status": "active",
        "chassis_number": "MA3ERLF1S00123456",
        "engine_number": "K12MN1234567",
        "address": "14 Ellisbridge, Ahmedabad, Gujarat",
        "insurance_valid_until": "2026-06-13",
    },
    "GJ05CD5678": {
        "plate": "GJ05CD5678",
        "owner_name": "Meera Shah",
        "vehicle_class": "MCWG",
        "make_model": "Bajaj Pulsar 150",
        "registration_date": "2021-02-02",
        "rc_status": "active",
        "chassis_number": "MD2A11GY9K123789",
        "engine_number": "DHXS12345678",
        "address": "Race Course Road, Vadodara, Gujarat",
        "insurance_valid_until": "2025-02-01",
    },
    "GJ27EF9012": {
        "plate": "GJ27EF9012",
        "owner_name": "Suresh Chauhan",
        "vehicle_class": "HGV",
        "make_model": "Tata 407",
        "registration_date": "2016-11-20",
        "rc_status": "suspended",
        "chassis_number": "MAT448024H1P12345",
        "engine_number": "497TC98765432",
        "address": "GIDC Industrial Estate, Surat, Gujarat",
        "insurance_valid_until": "2023-11-19",
    },
}


def _default_transport() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.headers.get("x-api-key") != "mock-vahan-key":
            return httpx.Response(401, json={"error": "invalid api key"})
        plate = request.url.params.get("plate", "")
        record = _MOCK_VEHICLES.get(plate.upper())
        if record is None:
            return httpx.Response(404, json={"error": "not found"})
        return httpx.Response(200, json=record)

    return httpx.MockTransport(handler)


class VahanProvider:
    """Vehicle registration lookups only — VAHAN has no licence, person or
    alert-push capability, so those three raise `OperationNotSupportedError`
    rather than guessing."""

    provider_id = "vahan"

    def __init__(
        self,
        *,
        base_url: str = "https://vahan.parivahan.gov.in",
        api_key: str = "mock-vahan-key",
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
        self._rate_limiter.acquire()
        started = time.monotonic()

        async def _call() -> httpx.Response:
            async with httpx.AsyncClient(
                base_url=self._base_url, timeout=self._timeout_s, transport=self._transport
            ) as client:
                return await client.get(
                    "/api/v1/vehicle",
                    params={"plate": plate.upper()},
                    headers={"x-api-key": self._api_key},
                )

        resp = await with_retry(_call, circuit_breaker=self._circuit_breaker)
        record = VehicleRecord(**resp.json()) if resp.status_code == 200 else None
        self._audit("lookup_vehicle", {"plate": plate}, record, time.monotonic() - started)
        return record

    async def lookup_licence(self, dl_number: str) -> LicenceRecord | None:
        raise OperationNotSupportedError(
            "VAHAN does not provide licence lookups — see SarthiProvider"
        )

    async def lookup_person(self, query: PersonQuery) -> list[PersonRecord]:
        raise OperationNotSupportedError("VAHAN does not provide person lookups")

    async def push_alert(
        self, *, case_reference: str, summary: str, priority: str = "normal"
    ) -> AlertPushResult:
        raise OperationNotSupportedError("VAHAN does not accept pushed alerts")

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
