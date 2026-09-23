"""Tests for M12's signed, time-limited media URLs."""

from __future__ import annotations

import time

from pydantic import SecretStr

from core_api.security.signed_urls import sign_media_path, verify_media_signature
from sentinel_core.config import Settings


def _settings(secret: str = "test-signing-secret") -> Settings:
    return Settings(media_url_signing_secret=SecretStr(secret))


def test_a_freshly_signed_url_verifies_successfully() -> None:
    settings = _settings()
    path = "/api/v1/detections/evt-001/snapshot"

    query = sign_media_path(path, settings=settings, expires_in_s=3600)
    expires_str, _, signature = query.replace("expires=", "").partition("&signature=")

    assert verify_media_signature(
        path, expires=int(expires_str), signature=signature, settings=settings
    )


def test_an_expired_signature_is_rejected() -> None:
    settings = _settings()
    path = "/api/v1/detections/evt-001/snapshot"

    query = sign_media_path(path, settings=settings, expires_in_s=-10)  # already expired
    expires_str, _, signature = query.replace("expires=", "").partition("&signature=")

    assert not verify_media_signature(
        path, expires=int(expires_str), signature=signature, settings=settings
    )


def test_a_tampered_path_is_rejected() -> None:
    """The signature covers the exact resource path — a signed URL for one
    resource can't be replayed against a different one."""
    settings = _settings()
    query = sign_media_path("/api/v1/detections/evt-001/snapshot", settings=settings)
    expires_str, _, signature = query.replace("expires=", "").partition("&signature=")

    assert not verify_media_signature(
        "/api/v1/detections/evt-002/snapshot",
        expires=int(expires_str),
        signature=signature,
        settings=settings,
    )


def test_a_tampered_signature_is_rejected() -> None:
    settings = _settings()
    path = "/api/v1/detections/evt-001/snapshot"
    query = sign_media_path(path, settings=settings)
    expires_str, _, signature = query.replace("expires=", "").partition("&signature=")

    tampered = signature[:-4] + ("0000" if signature[-4:] != "0000" else "1111")

    assert not verify_media_signature(
        path, expires=int(expires_str), signature=tampered, settings=settings
    )


def test_a_signature_from_a_different_secret_is_rejected() -> None:
    """Simulates a signature minted before a secret rotation."""
    path = "/api/v1/detections/evt-001/snapshot"
    query = sign_media_path(path, settings=_settings("old-secret"))
    expires_str, _, signature = query.replace("expires=", "").partition("&signature=")

    assert not verify_media_signature(
        path, expires=int(expires_str), signature=signature, settings=_settings("new-secret")
    )


def test_expiry_is_actually_in_the_future_by_the_requested_window() -> None:
    settings = _settings()
    before = int(time.time())

    query = sign_media_path("/x", settings=settings, expires_in_s=120)
    expires_str = query.split("&")[0].removeprefix("expires=")

    assert before + 120 <= int(expires_str) <= before + 121
