"""eGujCop provider — a contract-shaped mock for Gujarat Police's own
case/FIR cross-reference system. Unlike VAHAN/SARTHI, eGujCop is a police
system this platform would genuinely integrate bidirectionally with: it
answers person lookups (active FIRs, wanted flags) *and* accepts pushed
alerts (a stolen-vehicle hit broadcast to the control room / other
jurisdictions), matching docs/01-ARCHITECTURE.md §6.4's `push_alert(...)`.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
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

__all__ = ["EGujCopProvider"]

logger = logging.getLogger(__name__)

_MOCK_PERSONS: list[dict[str, object]] = [
    {
        "person_id": "EGC-2023-004521",
        "full_name": "Suresh Chauhan",
        "flags": ["active-FIR", "wanted"],
        "case_references": ["FIR/2023/GJ27/00812", "FIR/2024/GJ27/00119"],
        "source": "egujcop",
    },
    {
        "person_id": "EGC-2019-001187",
        "full_name": "Anil Vaghela",
        "flags": ["history-sheeter"],
        "case_references": ["FIR/2019/GJ01/00456"],
        "source": "egujcop",
    },
]


def _default_transport() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.headers.get("x-api-key") != "mock-egujcop-key":
            return httpx.Response(401, json={"error": "invalid api key"})

        if request.url.path == "/api/v1/alerts" and request.method == "POST":
            payload = json.loads(request.content)
            return httpx.Response(
                200,
                json={
                    "accepted": True,
                    "reference_id": f"EGC-ALERT-{uuid.uuid4().hex[:8].upper()}",
                    "detail": f"Broadcast to control room: {payload.get('summary', '')[:80]}",
                },
            )

        name_query = (request.url.params.get("full_name") or "").strip().lower()
        id_query = request.url.params.get("identifier")
        matches = [
            person
            for person in _MOCK_PERSONS
            if (name_query and name_query in str(person["full_name"]).lower())
            or (id_query and id_query == person["person_id"])
        ]
        return httpx.Response(
            200,
            json={
                "matches": [{**p, "match_confidence": 0.95 if id_query else 0.7} for p in matches]
            },
        )

    return httpx.MockTransport(handler)


class EGujCopProvider:
    """Person lookups and outbound alert pushes — no vehicle/licence
    capability of its own (VAHAN/SARTHI own those)."""

    provider_id = "egujcop"

    def __init__(
        self,
        *,
        base_url: str = "https://egujcop.gujarat.gov.in",
        api_key: str = "mock-egujcop-key",
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
            "eGujCop does not provide vehicle lookups — see VahanProvider"
        )

    async def lookup_licence(self, dl_number: str) -> LicenceRecord | None:
        raise OperationNotSupportedError(
            "eGujCop does not provide licence lookups — see SarthiProvider"
        )

    async def lookup_person(self, query: PersonQuery) -> list[PersonRecord]:
        self._rate_limiter.acquire()
        started = time.monotonic()

        async def _call() -> httpx.Response:
            params = {
                k: v
                for k, v in {
                    "full_name": query.full_name,
                    "identifier": query.identifier,
                }.items()
                if v
            }
            async with httpx.AsyncClient(
                base_url=self._base_url, timeout=self._timeout_s, transport=self._transport
            ) as client:
                return await client.get(
                    "/api/v1/persons", params=params, headers={"x-api-key": self._api_key}
                )

        resp = await with_retry(_call, circuit_breaker=self._circuit_breaker)
        records = [PersonRecord(**m) for m in resp.json().get("matches", [])]
        self._audit(
            "lookup_person",
            query.model_dump(exclude_none=True),
            records,
            time.monotonic() - started,
        )
        return records

    async def push_alert(
        self, *, case_reference: str, summary: str, priority: str = "normal"
    ) -> AlertPushResult:
        self._rate_limiter.acquire()
        started = time.monotonic()

        async def _call() -> httpx.Response:
            async with httpx.AsyncClient(
                base_url=self._base_url, timeout=self._timeout_s, transport=self._transport
            ) as client:
                return await client.post(
                    "/api/v1/alerts",
                    json={
                        "case_reference": case_reference,
                        "summary": summary,
                        "priority": priority,
                    },
                    headers={"x-api-key": self._api_key},
                )

        resp = await with_retry(_call, circuit_breaker=self._circuit_breaker)
        result = AlertPushResult(**resp.json())
        self._audit(
            "push_alert",
            {"case_reference": case_reference, "priority": priority},
            result,
            time.monotonic() - started,
        )
        return result

    def _audit(
        self, operation: str, query: dict[str, object], record: object, elapsed_s: float
    ) -> None:
        found = bool(record) if isinstance(record, list) else record is not None
        event = RegistryAuditEvent(
            provider_id=self.provider_id,
            operation=operation,
            query=query,
            found=found,
            latency_ms=elapsed_s * 1000,
            requested_at=datetime.now(UTC),
        )
        logger.info("gov_registry_audit", extra={"audit_event": event.model_dump(mode="json")})
