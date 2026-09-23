"""Signed, time-limited media URLs — docs/05-DELIVERY-PLAN.md's M12 bullet.
`<video>`/`<img>` tags can't attach an `Authorization` header, so evidence
clips and snapshots need a way to be embedded directly in markup without
either leaving the route unauthenticated or baking a long-lived bearer
token into a URL. A signed URL with a short expiry is the standard answer:
anyone with the link can view that one resource until it expires, and
nothing else.
"""

from __future__ import annotations

import hashlib
import hmac
import time

from sentinel_core.config import Settings

__all__ = ["sign_media_path", "verify_media_signature"]


def _signature(*, resource_path: str, expires_at: int, secret: str) -> str:
    message = f"{resource_path}:{expires_at}".encode()
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def sign_media_path(resource_path: str, *, settings: Settings, expires_in_s: int = 3600) -> str:
    """Returns the query string (`expires=...&signature=...`) to append to
    `resource_path`. `resource_path` should be the exact request path
    (e.g. `/api/v1/evidence/clips/<id>/video`) — the signature covers it
    verbatim, so a signed URL for one resource can't be replayed against a
    different one."""
    expires_at = int(time.time()) + expires_in_s
    secret = settings.media_url_signing_secret.get_secret_value()
    signature = _signature(resource_path=resource_path, expires_at=expires_at, secret=secret)
    return f"expires={expires_at}&signature={signature}"


def verify_media_signature(
    resource_path: str, *, expires: int, signature: str, settings: Settings
) -> bool:
    """Constant-time comparison (`hmac.compare_digest`) — a signature check
    that leaks timing information about *how much* of the signature
    matched is a real, if narrow, side channel."""
    if int(time.time()) > expires:
        return False
    secret = settings.media_url_signing_secret.get_secret_value()
    expected = _signature(resource_path=resource_path, expires_at=expires, secret=secret)
    return hmac.compare_digest(expected, signature)
