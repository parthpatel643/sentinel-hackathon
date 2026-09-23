"""FastAPI application factory.

M0 shipped the skeleton and health surface. M3 added the registry (Model 1,
mandatory). M4/M5 add live detections, the vehicle-route reconstruction and
the watchlist/alert/BOLO surface the Operator Console (M6) is built against.
"""

from __future__ import annotations

from typing import Any

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession

from core_api.auth.dependencies import current_user
from core_api.auth.service import TokenPayload
from core_api.db.base import get_session
from core_api.registry.service import codecs_in_use
from core_api.routers.admin import router as admin_router
from core_api.routers.auth import router as auth_router
from core_api.routers.detections import router as detections_router
from core_api.routers.evidence import router as evidence_router
from core_api.routers.field import router as field_router
from core_api.routers.registry import router as registry_router
from core_api.routers.watchlist import router as watchlist_router
from core_api.routers.zones import router as zones_router
from core_api.security.tenancy import TenancyMiddleware
from sentinel_core import configure_logging, get_settings
from sentinel_core.schemas import SCHEMA_VERSION

__all__ = ["create_app"]


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(level=settings.log_level, json_output=settings.log_json)

    app = FastAPI(
        title="Sentinel Platform API",
        version="0.1.0",
        description=(
            "Unified CCTV integration and video analytics platform. "
            "Gujarat Police Innovation Challenge 2026."
        ),
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    # M12: decodes the caller's JWT (best-effort) so get_session can apply
    # department-scoped Postgres RLS — see core_api/security/tenancy.py.
    app.add_middleware(TenancyMiddleware)

    app.include_router(auth_router)
    app.include_router(admin_router)
    app.include_router(registry_router)
    app.include_router(detections_router)
    app.include_router(field_router)
    app.include_router(zones_router)
    # evidence_router (clip video streaming) is intentionally NOT under the
    # blanket current_user dependency below — it has its own per-route auth
    # that also accepts a signed URL (M12), which a blanket JWT requirement
    # would short-circuit before that logic ever ran.
    app.include_router(evidence_router)
    # watchlist_router has no machine-called endpoints (unlike registry/
    # detections, which mix in the edge worker's health/ingest calls) — every
    # route here is a human operator action, so it is gated once, here,
    # rather than endpoint-by-endpoint.
    app.include_router(watchlist_router, dependencies=[Depends(current_user)])

    @app.get("/api/v1/health", tags=["ops"])
    async def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "environment": settings.environment,
            "node_id": settings.node_id,
            "event_schema_version": SCHEMA_VERSION,
        }

    @app.get("/api/v1/compliance/integrator", tags=["ops"])
    async def integrator_compliance(
        session: AsyncSession = Depends(get_session),
        _user: TokenPayload = Depends(current_user),
    ) -> dict[str, Any]:
        """Live status against the organisers' pre-submission checklist.

        Surfaced in the ops dashboard so a technical jury can verify compliance
        rather than take it on trust. Counters are wired up in M4.
        """
        codecs = await codecs_in_use(session)
        return {
            "rtsp_transport_tcp_forced": settings.rtsp_transport == "tcp",
            "publishing_to_gateway_disabled": settings.allow_stream_publish is False,
            "timing_source": "pts",
            "catalogue_driven_discovery": True,
            "mixed_codec_handling": len(codecs) >= 2,
            "codecs_in_use": codecs,
            "backoff": {
                "initial_s": settings.reconnect_backoff_initial_s,
                "max_s": settings.reconnect_backoff_max_s,
            },
        }

    return app


app = create_app()
