"""mTLS edge-identity trust — see sentinel_core.config's
`mtls_gateway_shared_secret` docstring for the full rationale (TLS
termination at a reverse proxy, not in-app, plus a shared secret to stop
header-spoofing on any request that reaches core_api directly).
"""

from __future__ import annotations

from fastapi import Header

from sentinel_core.config import get_settings

__all__ = ["edge_gateway_identity", "extract_cn"]


def extract_cn(subject_dn: str) -> str | None:
    """nginx's `$ssl_client_s_dn` gives the whole certificate subject as a
    comma-separated `CN=...,O=...` string (RFC 2253-ish, most specific
    component first) — there is no separate "just the CN" nginx variable,
    so core_api parses it out itself."""
    for component in subject_dn.split(","):
        key, _, value = component.strip().partition("=")
        if key.strip().upper() == "CN":
            return value.strip() or None
    return None


async def edge_gateway_identity(
    x_client_dn: str | None = Header(default=None),
    x_edge_gateway_secret: str | None = Header(default=None),
) -> str | None:
    """Returns the mTLS-verified edge node's certificate CN — but only when
    `x_edge_gateway_secret` matches this deployment's configured secret,
    proving the header genuinely came from the trusted gateway rather than
    being spoofed by whoever is calling core_api directly. Returns `None`
    (never raises) for any request that didn't go through the gateway —
    this is enrichment for audit trails, not an authorization gate; the
    endpoint's own auth (`require_service_token` / a user JWT) is
    unaffected either way.
    """
    if not x_client_dn or not x_edge_gateway_secret:
        return None
    settings = get_settings()
    if x_edge_gateway_secret != settings.mtls_gateway_shared_secret.get_secret_value():
        return None
    return extract_cn(x_client_dn)
