"""Tests for the mTLS edge-gateway identity-trust dependency — see
core_api/security/mtls.py's docstring for the shared-secret rationale."""

from __future__ import annotations

import pytest
from pydantic import SecretStr

from core_api.security.mtls import edge_gateway_identity, extract_cn
from sentinel_core.config import Settings


def _settings_with_secret(secret: str) -> Settings:
    return Settings(mtls_gateway_shared_secret=SecretStr(secret))


def test_extract_cn_from_a_typical_nginx_subject_dn() -> None:
    assert extract_cn("CN=edge-node-01,O=Sentinel Platform") == "edge-node-01"


def test_extract_cn_handles_cn_appearing_after_other_components() -> None:
    assert extract_cn("O=Sentinel Platform,CN=edge-node-02") == "edge-node-02"


def test_extract_cn_returns_none_when_there_is_no_cn_component() -> None:
    assert extract_cn("O=Sentinel Platform") is None


async def test_returns_none_when_no_headers_are_present() -> None:
    identity = await edge_gateway_identity(x_client_dn=None, x_edge_gateway_secret=None)

    assert identity is None


async def test_returns_none_when_only_the_dn_header_is_present() -> None:
    """A request that reaches core_api directly (bypassing the gateway)
    might carry an attacker-supplied X-Client-DN with no matching secret —
    must not be trusted."""
    identity = await edge_gateway_identity(
        x_client_dn="CN=edge-node-01,O=Sentinel Platform", x_edge_gateway_secret=None
    )

    assert identity is None


async def test_returns_none_when_the_secret_is_wrong(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "core_api.security.mtls.get_settings", lambda: _settings_with_secret("correct-secret")
    )

    identity = await edge_gateway_identity(
        x_client_dn="CN=edge-node-01,O=Sentinel Platform", x_edge_gateway_secret="wrong-secret"
    )

    assert identity is None


async def test_returns_the_cn_when_the_secret_matches(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "core_api.security.mtls.get_settings", lambda: _settings_with_secret("correct-secret")
    )

    identity = await edge_gateway_identity(
        x_client_dn="CN=edge-node-01,O=Sentinel Platform", x_edge_gateway_secret="correct-secret"
    )

    assert identity == "edge-node-01"
