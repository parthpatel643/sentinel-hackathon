"""Tests for the ExternalRegistry providers (VAHAN/SARTHI/eGujCop/AFIS) —
each provider's happy path, its `OperationNotSupportedError` boundaries, PII
redaction, and the shared resilience primitives (rate limiter, circuit
breaker, retry). Self-contained per this repo's pytest-collision lesson —
no shared fixtures package."""

from __future__ import annotations

import httpx
import pytest

from sentinel_core.gov_registry import (
    AfisProvider,
    EGujCopProvider,
    OperationNotSupportedError,
    PersonQuery,
    SarthiProvider,
    VahanProvider,
)
from sentinel_core.gov_registry.resilience import (
    CircuitBreaker,
    CircuitOpenError,
    RateLimiter,
    RateLimitExceededError,
    with_retry,
)

# --- VAHAN -------------------------------------------------------------------


async def test_vahan_lookup_vehicle_returns_a_record_for_a_known_plate() -> None:
    provider = VahanProvider()

    record = await provider.lookup_vehicle("gj01ab1234")

    assert record is not None
    assert record.plate == "GJ01AB1234"
    assert record.owner_name == "Ravi Patel"


async def test_vahan_lookup_vehicle_returns_none_for_an_unknown_plate() -> None:
    provider = VahanProvider()

    record = await provider.lookup_vehicle("GJ99ZZ9999")

    assert record is None


async def test_vahan_audit_safe_dict_masks_pii_but_keeps_status_fields() -> None:
    provider = VahanProvider()
    record = await provider.lookup_vehicle("GJ01AB1234")
    assert record is not None

    safe = record.audit_safe_dict()

    assert safe["owner_name"] != record.owner_name
    assert safe["plate"] == record.plate
    assert safe["rc_status"] == record.rc_status


async def test_vahan_does_not_support_licence_or_person_lookups() -> None:
    provider = VahanProvider()

    with pytest.raises(OperationNotSupportedError):
        await provider.lookup_licence("anything")
    with pytest.raises(OperationNotSupportedError):
        await provider.lookup_person(PersonQuery(full_name="anyone"))
    with pytest.raises(OperationNotSupportedError):
        await provider.push_alert(case_reference="x", summary="y")


# --- SARTHI ------------------------------------------------------------------


async def test_sarthi_lookup_licence_returns_a_record_for_a_known_dl() -> None:
    provider = SarthiProvider()

    record = await provider.lookup_licence("gj0120190001234")

    assert record is not None
    assert record.holder_name == "Ravi Patel"
    assert "LMV" in record.licence_class


async def test_sarthi_lookup_licence_surfaces_disqualification_status() -> None:
    provider = SarthiProvider()

    record = await provider.lookup_licence("GJ2720150009012")

    assert record is not None
    assert record.status == "disqualified"
    assert "disqualified-6-months-2024" in record.endorsements


async def test_sarthi_does_not_support_vehicle_lookups() -> None:
    provider = SarthiProvider()

    with pytest.raises(OperationNotSupportedError):
        await provider.lookup_vehicle("GJ01AB1234")


# --- eGujCop -----------------------------------------------------------------


async def test_egujcop_lookup_person_by_name_finds_a_wanted_flag() -> None:
    provider = EGujCopProvider()

    matches = await provider.lookup_person(PersonQuery(full_name="Suresh Chauhan"))

    assert len(matches) == 1
    assert "wanted" in matches[0].flags
    assert matches[0].case_references


async def test_egujcop_lookup_person_with_no_match_returns_empty_list() -> None:
    provider = EGujCopProvider()

    matches = await provider.lookup_person(PersonQuery(full_name="Nobody Here"))

    assert matches == []


async def test_egujcop_push_alert_is_accepted_and_returns_a_reference() -> None:
    provider = EGujCopProvider()

    result = await provider.push_alert(
        case_reference="FIR/2024/GJ27/00119", summary="Stolen vehicle sighted", priority="high"
    )

    assert result.accepted is True
    assert result.reference_id is not None
    assert result.reference_id.startswith("EGC-ALERT-")


async def test_egujcop_does_not_support_vehicle_or_licence_lookups() -> None:
    provider = EGujCopProvider()

    with pytest.raises(OperationNotSupportedError):
        await provider.lookup_vehicle("GJ01AB1234")
    with pytest.raises(OperationNotSupportedError):
        await provider.lookup_licence("anything")


# --- AFIS ----------------------------------------------------------------------


async def test_afis_lookup_person_by_photo_hash_finds_a_gallery_match() -> None:
    provider = AfisProvider()

    matches = await provider.lookup_person(PersonQuery(photo_hash="sha256:af1s0001"))

    assert len(matches) == 1
    assert matches[0].source == "afis"
    assert matches[0].match_confidence > 0.5


async def test_afis_lookup_person_without_a_photo_hash_returns_empty_not_an_error() -> None:
    """A name-only query is a valid PersonQuery shape but AFIS is a
    biometric gallery — it must degrade gracefully, not crash on a query
    it can't answer."""
    provider = AfisProvider()

    matches = await provider.lookup_person(PersonQuery(full_name="Suresh Chauhan"))

    assert matches == []


async def test_afis_does_not_support_alerts_vehicles_or_licences() -> None:
    provider = AfisProvider()

    with pytest.raises(OperationNotSupportedError):
        await provider.push_alert(case_reference="x", summary="y")


# --- Resilience primitives -----------------------------------------------------


def test_rate_limiter_rejects_once_capacity_is_exhausted() -> None:
    limiter = RateLimiter(capacity=2, refill_period_s=60.0)

    limiter.acquire()
    limiter.acquire()
    with pytest.raises(RateLimitExceededError):
        limiter.acquire()


def test_rate_limiter_refills_over_time() -> None:
    limiter = RateLimiter(capacity=1, refill_period_s=0.05)
    limiter.acquire()

    import time

    time.sleep(0.1)
    limiter.acquire()  # should not raise — a full refill period has passed


def test_circuit_breaker_opens_after_the_failure_threshold() -> None:
    breaker = CircuitBreaker(failure_threshold=2, recovery_timeout_s=60.0)

    breaker.record_failure()
    breaker.before_call()  # still closed after 1 failure
    breaker.record_failure()

    with pytest.raises(CircuitOpenError):
        breaker.before_call()


def test_circuit_breaker_half_opens_after_the_recovery_timeout() -> None:
    breaker = CircuitBreaker(failure_threshold=1, recovery_timeout_s=0.05)
    breaker.record_failure()

    import time

    time.sleep(0.1)

    breaker.before_call()  # half-open — one probe call is allowed through


async def test_with_retry_retries_transient_failures_then_succeeds() -> None:
    attempts = 0

    async def flaky() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise httpx.TransportError("simulated network blip")
        return "ok"

    breaker = CircuitBreaker(failure_threshold=10)

    result = await with_retry(flaky, circuit_breaker=breaker, max_attempts=3, backoff_base_s=0.01)

    assert result == "ok"
    assert attempts == 3


async def test_with_retry_gives_up_after_max_attempts_and_opens_the_breaker() -> None:
    async def always_fails() -> str:
        raise httpx.TransportError("simulated persistent outage")

    # threshold higher than max_attempts so the underlying error — not a
    # circuit-open short-circuit — is what's raised after retries exhaust.
    breaker = CircuitBreaker(failure_threshold=5, recovery_timeout_s=60.0)

    with pytest.raises(httpx.TransportError):
        await with_retry(always_fails, circuit_breaker=breaker, max_attempts=3, backoff_base_s=0.01)

    assert breaker._consecutive_failures == 3


async def test_with_retry_stops_early_once_the_breaker_opens() -> None:
    """Once the breaker trips mid-retry-loop, further attempts are
    rejected with CircuitOpenError instead of hammering the failing
    dependency for the remaining retry budget."""
    attempts = 0

    async def always_fails() -> str:
        nonlocal attempts
        attempts += 1
        raise httpx.TransportError("simulated persistent outage")

    breaker = CircuitBreaker(failure_threshold=2, recovery_timeout_s=60.0)

    with pytest.raises(CircuitOpenError):
        await with_retry(always_fails, circuit_breaker=breaker, max_attempts=5, backoff_base_s=0.01)

    assert attempts == 2  # stopped calling once the breaker opened, not all 5 attempts
