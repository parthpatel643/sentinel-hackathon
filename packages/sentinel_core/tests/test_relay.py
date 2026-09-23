"""Tests for the shared relay-path helpers.

The behaviour these pin down is not cosmetic: getting it wrong means either
two connections per camera to the government gateway (the bug this module
exists to fix, which burns a metered viewing quota twice as fast) or a
needless republish of a stream we already host.
"""

from __future__ import annotations

import json

import httpx
import pytest

from sentinel_core.config import Settings
from sentinel_core.relay import (
    ensure_relay_path,
    is_relay_hosted,
    relay_hls_url,
    relay_path_for,
    relay_rtsp_url,
    release_relay_path,
)

EXTERNAL = "rtsp://user:pass@103.250.160.189:8554/stream/cam01"


@pytest.fixture
def settings() -> Settings:
    return Settings(
        relay_rtsp_url="rtsp://localhost:8554",
        relay_hls_url="http://localhost:8888",
        relay_api_url="http://localhost:9997",
    )


def test_synthetic_grid_cameras_are_recognised_as_already_relayed(settings: Settings) -> None:
    """The synthetic grid publishes straight into our relay. Republishing it
    would be a relay pulling from itself."""
    assert is_relay_hosted("rtsp://127.0.0.1:8554/dev/dev-cam-01", settings) is True
    assert is_relay_hosted("rtsp://localhost:8554/dev/dev-cam-01", settings) is True


def test_a_government_camera_is_not_relay_hosted(settings: Settings) -> None:
    assert is_relay_hosted(EXTERNAL, settings) is False


def test_the_same_host_on_a_different_port_is_not_our_relay(settings: Settings) -> None:
    """A different port is a different server, even on this machine."""
    assert is_relay_hosted("rtsp://localhost:9554/dev/x", settings) is False


def test_path_names_strip_characters_mediamtx_rejects(settings: Settings) -> None:
    """MediaMTX accepts only alphanumerics, underscore, dot, minus and slash
    in a path name, and returns 400 for anything else — a camera id with a
    colon or space must not become a failed relay registration."""
    assert relay_path_for("cam01", settings) == "ext/cam01"
    assert relay_path_for("cam 01:a", settings) == "ext/cam-01-a"


def test_urls_are_built_against_the_configured_relay(settings: Settings) -> None:
    assert relay_rtsp_url("ext/cam01", settings) == "rtsp://localhost:8554/ext/cam01"
    assert relay_hls_url("ext/cam01", settings) == "http://localhost:8888/ext/cam01/index.m3u8"


async def test_an_existing_path_is_reused_rather_than_re_added(settings: Settings) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method != "POST", "an existing path must never be re-added"
        assert request.method == "GET"
        # MediaMTX always reports the mode, and it already matches what this
        # caller wants, so there is nothing to reconcile either.
        return httpx.Response(200, json={"name": "ext/cam01", "sourceOnDemand": True})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        assert await ensure_relay_path(
            rtsp_url=EXTERNAL, path_name="ext/cam01", settings=settings, client=client
        )


async def test_a_missing_path_is_added_as_a_pull_source(settings: Settings) -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(404)
        import json

        seen.update(json.loads(request.content))
        return httpx.Response(200, json={"status": "ok"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        assert await ensure_relay_path(
            rtsp_url=EXTERNAL, path_name="ext/cam01", settings=settings, client=client
        )

    # `source` is what makes this a PULL: MediaMTX dials the camera as a
    # client. Nothing is ever published to the gateway.
    assert seen["source"] == EXTERNAL
    assert seen["rtspTransport"] == "tcp"
    assert seen["sourceOnDemand"] is True


async def test_on_demand_can_be_disabled_for_a_permanent_reader(settings: Settings) -> None:
    """The edge worker analyses continuously, so its paths must not tear
    themselves down between reconnects."""
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(404)
        import json

        seen.update(json.loads(request.content))
        return httpx.Response(200, json={"status": "ok"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await ensure_relay_path(
            rtsp_url=EXTERNAL,
            path_name="ext/cam01",
            settings=settings,
            client=client,
            on_demand=False,
        )

    assert seen["sourceOnDemand"] is False


async def test_a_racing_duplicate_add_counts_as_success(settings: Settings) -> None:
    """Two consumers can both see the path missing and both try to add it.
    The loser's 400 means the path exists, which is the desired end state."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(404)
        return httpx.Response(400, json={"status": "error", "error": "path already exists"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        assert await ensure_relay_path(
            rtsp_url=EXTERNAL, path_name="ext/cam01", settings=settings, client=client
        )


async def test_an_unreachable_relay_reports_failure_without_raising(settings: Settings) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        assert not await ensure_relay_path(
            rtsp_url=EXTERNAL, path_name="ext/cam01", settings=settings, client=client
        )


async def test_an_unexpected_relay_error_reports_failure(settings: Settings) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(404)
        return httpx.Response(500, text="boom")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        assert not await ensure_relay_path(
            rtsp_url=EXTERNAL, path_name="ext/cam01", settings=settings, client=client
        )


async def test_an_existing_path_is_reconciled_to_the_mode_the_caller_asked_for(
    settings: Settings,
) -> None:
    """Whoever created the path first used to decide its mode forever. That
    made `sourceOnDemand` sticky, so a path left pinned open by an earlier run
    stayed pinned — the leak that quietly drains the gateway's quota."""
    patched: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, json={"name": "ext/cam01", "sourceOnDemand": True})
        if request.method == "PATCH":
            patched.update(json.loads(request.content))
            return httpx.Response(200)
        raise AssertionError(f"unexpected {request.method} {request.url}")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        assert await ensure_relay_path(
            rtsp_url=EXTERNAL,
            path_name="ext/cam01",
            settings=settings,
            client=client,
            on_demand=False,
        )

    assert patched == {"sourceOnDemand": False}


async def test_a_path_already_in_the_right_mode_is_left_alone(settings: Settings) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, json={"name": "ext/cam01", "sourceOnDemand": True})
        raise AssertionError(f"should not have written: {request.method} {request.url}")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        assert await ensure_relay_path(
            rtsp_url=EXTERNAL, path_name="ext/cam01", settings=settings, client=client
        )


async def test_releasing_a_path_puts_it_back_on_demand(settings: Settings) -> None:
    """The upstream connection is what costs quota, and MediaMTX only drops it
    once the path is on-demand and the last reader has gone."""
    patched: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "PATCH"
        assert "ext/cam01" in str(request.url)
        patched.update(json.loads(request.content))
        return httpx.Response(200)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        assert await release_relay_path(
            path_name="ext/cam01", settings=settings, client=client
        )

    assert patched == {"sourceOnDemand": True}


async def test_releasing_never_raises_when_the_relay_has_gone(settings: Settings) -> None:
    """Release runs on a shutdown path; a relay that is already gone has, in
    effect, released the path anyway."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        assert not await release_relay_path(
            path_name="ext/cam01", settings=settings, client=client
        )
