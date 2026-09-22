"""Government catalogue client — `GET cameras.json`.

The catalogue is the single source of truth for which cameras exist; ids are
never hard-coded anywhere in this codebase (see the compliance suite). Every
run starts here, and the driver architecture in docs/01-ARCHITECTURE.md means
this module only has to map catalogue entries into CameraDescriptor — nothing
downstream needs to know the catalogue's exact wire format.

SCHEMA CAVEAT: the integrator guide documents the endpoints and access model
precisely, but not the exact JSON shape of `cameras.json` itself. The parser
below is intentionally tolerant (unknown fields are ignored, a best-effort set
of common key aliases is tried for each value, and one malformed entry never
aborts the whole batch) so that once real credentials are available this needs
verification and light adjustment, not a rewrite. Run
`scripts/verify_gov_catalogue.py` against the real endpoint to confirm or
correct the mapping.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from sentinel_core.config import Settings
from sentinel_core.schemas import (
    AnalyticsTier,
    CameraDescriptor,
    CameraStatus,
    GeoPoint,
    SourceCapabilities,
    StreamProfile,
    StreamProtocol,
)

__all__ = ["CatalogueEntryError", "GovCatalogueClient"]

logger = logging.getLogger(__name__)

# Common key aliases seen across similar government-portal catalogues. Tried
# in order; the first present key wins. Extend this list rather than assuming
# one exact name once the real response is confirmed.
_ID_KEYS = ("id", "camera_id", "cameraId", "camId")
_NAME_KEYS = ("name", "label", "title", "cameraName")
_DEPARTMENT_KEYS = ("department", "dept", "agency")
_SITE_KEYS = ("site", "location_name", "locationName", "address")
_LAT_KEYS = ("lat", "latitude")
_LON_KEYS = ("lon", "lng", "longitude")
_CODEC_KEYS = ("codec", "video_codec", "videoCodec")
_WIDTH_KEYS = ("width", "res_width", "resolution_width")
_HEIGHT_KEYS = ("height", "res_height", "resolution_height")
_FPS_KEYS = ("fps", "frame_rate", "frameRate", "declared_fps")
_LIVE_KEYS = ("live", "is_live", "status", "online")

# The real catalogue's entries carry only `id` and `name` — no coordinates at
# all — which otherwise leaves every onboarded camera unplottable on the map.
# Many names do contain a real, recognisable Gujarat place; this is a
# best-effort *town/landmark-level* lookup (not the camera's actual GPS
# position, which the catalogue simply doesn't provide) applied only when a
# name clearly matches one of these places — an ambiguous or generic name
# ("Suvidha park", "kheram", "Mohanpura") is deliberately left unplotted
# rather than guessed. Longer/more specific keys are checked first so
# "Rajkot Bus Port" doesn't fall through to a shorter unrelated match.
_GUJARAT_PLACE_COORDS: tuple[tuple[str, float, float], ...] = (
    ("paldi", 23.0134, 72.5589),
    ("visat", 23.0862, 72.5847),
    ("chiman bhai bridge", 23.0300, 72.5800),
    ("cn vidhyalaya", 23.0167, 72.5500),
    ("adalaj", 23.1667, 72.5833),
    ("junagadh", 21.5222, 70.4579),
    ("gir-somnath", 20.9000, 70.4000),
    ("gir somnath", 20.9000, 70.4000),
    ("rajkot", 22.3039, 70.8022),
    ("navsari", 20.9467, 72.9520),
    ("gandevi", 20.8000, 72.9167),
    ("patan", 23.8493, 72.1266),
    ("dehgam", 23.1667, 72.8167),
    ("bilimora", 20.7667, 72.9500),
    ("gandhidham", 23.0753, 70.1337),
)


def _geocode_from_name(name: str) -> GeoPoint | None:
    lowered = name.lower()
    for keyword, lat, lon in _GUJARAT_PLACE_COORDS:
        if keyword in lowered:
            return GeoPoint(lat=lat, lon=lon)
    return None


class CatalogueEntryError(ValueError):
    """One entry in the catalogue could not be mapped to a CameraDescriptor.

    Raised per-entry and caught by the batch fetch — a single malformed row
    must never prevent onboarding every other camera in the catalogue.
    """


def _first(raw: dict[str, Any], keys: tuple[str, ...]) -> Any | None:
    for key in keys:
        if key in raw and raw[key] not in (None, ""):
            return raw[key]
    return None


def _looks_live(raw: dict[str, Any]) -> CameraStatus:
    value = _first(raw, _LIVE_KEYS)
    if value is None:
        return CameraStatus.UNKNOWN
    if isinstance(value, bool):
        return CameraStatus.LIVE if value else CameraStatus.DOWN
    if isinstance(value, str):
        return (
            CameraStatus.LIVE
            if value.lower() in {"live", "online", "up", "true"}
            else CameraStatus.DOWN
        )
    return CameraStatus.UNKNOWN


def _parse_entry(raw: dict[str, Any], settings: Settings) -> CameraDescriptor:
    camera_id = _first(raw, _ID_KEYS)
    if not camera_id:
        raise CatalogueEntryError(f"entry has none of {_ID_KEYS}: {raw!r}")
    camera_id = str(camera_id)

    lat = _first(raw, _LAT_KEYS)
    lon = _first(raw, _LON_KEYS)
    location: GeoPoint | None
    if lat is not None and lon is not None:
        location = GeoPoint(lat=float(lat), lon=float(lon))
    else:
        location = _geocode_from_name(str(_first(raw, _NAME_KEYS) or ""))

    width = _first(raw, _WIDTH_KEYS)
    height = _first(raw, _HEIGHT_KEYS)
    fps = _first(raw, _FPS_KEYS)

    profiles = [
        StreamProfile(
            protocol=StreamProtocol.RTSP,
            url=settings.gov_stream_url("rtsp", camera_id),
            codec=_first(raw, _CODEC_KEYS),
            width=int(width) if width is not None else None,
            height=int(height) if height is not None else None,
            declared_fps=float(fps) if fps is not None else None,
        ),
        StreamProfile(
            protocol=StreamProtocol.WHEP,
            url=settings.gov_stream_url("whep", camera_id),
        ),
        StreamProfile(
            protocol=StreamProtocol.HLS,
            url=settings.gov_hls_url(camera_id),
        ),
    ]

    return CameraDescriptor(
        camera_id=camera_id,
        name=str(_first(raw, _NAME_KEYS) or camera_id),
        driver_id="rtsp",
        department=_first(raw, _DEPARTMENT_KEYS),
        site=_first(raw, _SITE_KEYS),
        location=location,
        profiles=profiles,
        capabilities=SourceCapabilities(live=True, snapshot=False, playback=False),
        tier=AnalyticsTier.B_SAMPLED,
        status=_looks_live(raw),
        attributes={"source": "gov_catalogue"},
    )


class GovCatalogueClient:
    """Fetches and parses the government camera catalogue.

    Deliberately has no local cache and no hard-coded camera list: every call
    to `fetch()` re-reads the catalogue, so an added, removed or renamed
    camera is picked up on the next run without a code change.
    """

    def __init__(self, settings: Settings, *, client: httpx.AsyncClient | None = None) -> None:
        self._settings = settings
        self._client = client or httpx.AsyncClient(timeout=10.0)
        self._owns_client = client is None
        self._logged_in = False

    async def _ensure_authenticated(self) -> None:
        """The catalogue and HLS host sits behind a session-cookie login
        (`POST /auth/login` with `email`/`password` form fields) that the
        integrator guide doesn't document up front — discovered by reading
        the login page's own HTML form when a bare `GET cameras.json` kept
        302-redirecting there. RTSP/WHEP are unaffected: those authenticate
        per-connection via the URL, not this cookie. Logged in once per
        client instance, not once per fetch() call.
        """
        if self._logged_in or not self._settings.gov_access_email:
            return
        login_url = f"{self._settings.gov_hls_base_url}/auth/login"
        await self._client.post(
            login_url,
            data={
                "email": self._settings.gov_access_email,
                "password": self._settings.gov_access_password.get_secret_value(),
            },
        )
        self._logged_in = True

    async def fetch(self) -> list[CameraDescriptor]:
        """Fetch the catalogue and parse every entry it's possible to parse.

        A malformed entry is logged and skipped rather than aborting the
        whole onboarding run — one bad row must never block the other 29.
        """
        await self._ensure_authenticated()
        response = await self._client.get(self._settings.gov_catalogue_url)
        response.raise_for_status()
        payload = response.json()

        raw_entries = self._extract_entries(payload)
        cameras: list[CameraDescriptor] = []
        for raw in raw_entries:
            try:
                cameras.append(_parse_entry(raw, self._settings))
            except (CatalogueEntryError, TypeError, ValueError) as exc:
                logger.warning("skipping unparseable catalogue entry: %s", exc)
        return cameras

    @staticmethod
    def _extract_entries(payload: Any) -> list[dict[str, Any]]:
        """The catalogue might be a bare list or wrapped in an envelope key
        (`{"cameras": [...]}`, `{"items": [...]}`) — accept either shape."""
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            for key in ("cameras", "items", "data", "results"):
                value = payload.get(key)
                if isinstance(value, list):
                    return value
        raise CatalogueEntryError(f"unrecognised catalogue response shape: {type(payload)!r}")

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> GovCatalogueClient:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()
