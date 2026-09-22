"""FastAPI dependencies for auth-gated routes.

`current_user` is used per-endpoint (function-signature `Depends(...)`)
rather than blanket-applied at `include_router()` time: several routers mix
human-operator endpoints (need a real login) with machine endpoints the
edge worker calls (detection ingest, camera health heartbeats) — those use
`require_service_token` instead, since the worker has no user to log in as.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import Depends, Header, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from core_api.auth.service import InvalidTokenError, TokenPayload, decode_access_token
from sentinel_core.config import get_settings

__all__ = [
    "current_user",
    "current_user_or_service",
    "require_role",
    "require_service_token",
]

_bearer = HTTPBearer(auto_error=False)


async def current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> TokenPayload:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        return decode_access_token(credentials.credentials, get_settings())
    except InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc


def require_role(*roles: str) -> Callable[[TokenPayload], Awaitable[TokenPayload]]:
    """`Depends(require_role("admin"))` for the handful of routes that need
    more than "any logged-in user" (M12's fuller RBAC is the place for
    anything more granular than a flat role check)."""

    async def _check(user: TokenPayload = Depends(current_user)) -> TokenPayload:
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user

    return _check


async def require_service_token(
    x_service_token: str | None = Header(default=None),
) -> None:
    """Gate for the edge worker's machine-to-machine calls — a static
    shared secret, not a user JWT. Deliberately a separate, narrower
    credential: it can only ever hit the two-ish endpoints it's applied to,
    unlike a user token which (subject to role) reaches the whole API."""
    settings = get_settings()
    if x_service_token != settings.edge_service_token.get_secret_value():
        raise HTTPException(status_code=401, detail="Invalid or missing service token")


async def current_user_or_service(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    x_service_token: str | None = Header(default=None),
) -> TokenPayload | None:
    """`POST /cameras` is genuinely dual-use: a human onboarding a camera
    through the Admin wizard, and the edge worker registering a catalogue
    camera before it starts posting detections against it. Accepts either
    credential rather than forcing one call site to pretend to be the
    other. Returns None for the service-token path (there is no user)."""
    settings = get_settings()
    if x_service_token is not None:
        if x_service_token != settings.edge_service_token.get_secret_value():
            raise HTTPException(status_code=401, detail="Invalid service token")
        return None
    return await current_user(credentials)
