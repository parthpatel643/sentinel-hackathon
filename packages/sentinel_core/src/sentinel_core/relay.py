"""Local relay path management — one upstream connection per camera.

The integrator guide is explicit: *"Each connected client receives its own
copy of the stream. Open only the cameras you are actively processing."*

Before this module existed, Sentinel opened **two** connections to the
government gateway for any camera that was both analysed and previewed: the
edge worker dialled the camera's RTSP URL for analytics, and MediaMTX
separately dialled the *same* URL to republish it for the browser. Watching
six cameras we were already analysing therefore consumed twelve streams'
worth of the gateway's per-account viewing quota, and measurably accelerated
the cooldowns documented in `evidence/M14-EVIDENCE-RUN-FINDINGS.md`.

Registering the camera as a PULL source on our own MediaMTX and then having
*everything* — the analytics pipeline and every browser tile — read that
local path collapses those N connections back to one. That is what a relay
is for, and it makes "pace your load" structurally true rather than something
each call site has to remember.

Compliance is unaffected: MediaMTX dials the camera as an RTSP *client*,
exactly as the edge worker's own capture did. Nothing is ever published to
the gateway.

Shared by `core_api.registry.service` (which needs the HLS URL for a
browser) and `edge_agent.worker` (which needs the RTSP URL for analytics),
so the two cannot drift into managing relay paths differently.
"""

from __future__ import annotations

import logging
from urllib.parse import urlsplit

import httpx

from sentinel_core.config import Settings

__all__ = [
    "ensure_relay_path",
    "is_relay_hosted",
    "relay_hls_url",
    "relay_path_for",
    "relay_rtsp_url",
]

logger = logging.getLogger(__name__)

_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


def relay_path_for(camera_id: str, settings: Settings) -> str:
    """The MediaMTX path an external camera is republished under.

    MediaMTX path names accept only alphanumerics, underscore, dot, minus and
    slash, so anything else in a camera id is replaced rather than passed
    through to a 400 from its API.
    """
    safe = "".join(c if (c.isalnum() or c in "_.-") else "-" for c in camera_id)
    return f"{settings.relay_external_path_prefix}/{safe}"


def is_relay_hosted(url: str, settings: Settings) -> bool:
    """Whether `url` already points at our own relay, in which case it needs
    no republishing — the synthetic grid publishes straight into it.

    `localhost` and `127.0.0.1` are the same machine but not the same string;
    a raw netloc comparison treated the synthetic grid's cameras (registered
    as `127.0.0.1:8554`) as an unrecognised external source whenever
    `relay_rtsp_url` was configured with `localhost` instead, which is the
    default in `sentinel_core.config`.
    """
    relay = urlsplit(settings.relay_rtsp_url)
    parsed = urlsplit(url)
    if parsed.hostname is None or relay.hostname is None:
        return False
    same_host = parsed.hostname == relay.hostname or (
        parsed.hostname in _LOOPBACK_HOSTS and relay.hostname in _LOOPBACK_HOSTS
    )
    return same_host and parsed.port == relay.port


def relay_rtsp_url(path_name: str, settings: Settings) -> str:
    return f"{settings.relay_rtsp_url.rstrip('/')}/{path_name}"


def relay_hls_url(path_name: str, settings: Settings) -> str:
    return f"{settings.relay_hls_url.rstrip('/')}/{path_name}/index.m3u8"


async def ensure_relay_path(
    *,
    rtsp_url: str,
    path_name: str,
    settings: Settings,
    client: httpx.AsyncClient,
    on_demand: bool = True,
) -> bool:
    """Register `rtsp_url` on our own MediaMTX under `path_name` as a PULL
    source, so every consumer can read it locally.

    `on_demand=True` means MediaMTX does not dial the camera until the first
    reader arrives, so registering thirty cameras up front costs nothing until
    one is actually opened. The edge worker passes `on_demand=False` for
    cameras it is about to analyse continuously: it is a permanent reader, and
    letting the path tear itself down between reconnects would just add
    another dial to every recovery.

    Idempotent and safe under a race. If the path already exists — a
    concurrent request, or a previous run — MediaMTX's `add` returns 400 with
    a specific "path already exists" message, which is treated as success:
    the desired end state is that the path exists, and it does.

    Returns whether the path is now known to exist. Never raises: a MediaMTX
    outage must degrade to "this camera is unavailable", not take down the
    caller.
    """
    base = settings.relay_api_url.rstrip("/")
    try:
        existing = await client.get(f"{base}/v3/config/paths/get/{path_name}")
        if existing.status_code == 200:
            return True
        response = await client.post(
            f"{base}/v3/config/paths/add/{path_name}",
            json={
                "source": rtsp_url,
                "sourceOnDemand": on_demand,
                "rtspTransport": "tcp",
            },
        )
        if response.status_code == 200:
            return True
        if response.status_code == 400 and "already exists" in response.text:
            return True
        logger.warning(
            "MediaMTX refused to add relay path %r: %s %s",
            path_name,
            response.status_code,
            response.text,
        )
        return False
    except httpx.HTTPError as exc:
        logger.warning("could not reach the local relay to add path %r: %s", path_name, exc)
        return False
