"""Department-tenancy middleware — decodes the caller's JWT (best-effort,
never raises) before any route dependency runs, and stashes the
department_id claim onto `request.state` for `core_api.db.base.get_session`
to apply as the `app.current_department_id` GUC the RLS policies read.

A middleware, not a FastAPI `Depends()`, specifically so it runs ahead of
`get_session` regardless of dependency ordering, without changing every
route's signature to explicitly depend on both auth and the session in a
particular order. See docs/08-SECURITY-HARDENING.md.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from core_api.auth.service import InvalidTokenError, decode_access_token
from sentinel_core.config import get_settings

__all__ = ["TenancyMiddleware"]


class TenancyMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request.state.department_id = None
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[len("Bearer ") :]
            try:
                payload = decode_access_token(token, get_settings())
            except InvalidTokenError:
                # Not this middleware's job to reject a bad token — the
                # route's own auth dependency does that and returns a
                # proper 401. Failing open here just means "no department
                # scope applied," same as any unauthenticated/machine call.
                pass
            else:
                request.state.department_id = payload.department_id
        return await call_next(request)
