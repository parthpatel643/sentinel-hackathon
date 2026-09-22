"""GovCatalogueClient — schema-tolerant parsing of the government catalogue.

The exact response shape of `cameras.json` is unverified (see the module
docstring), so these tests exercise the tolerant-parsing contract: common key
aliases, an enveloped or bare-list response, and one bad entry never blocking
the rest — rather than asserting one specific schema is "the" schema.
"""

from __future__ import annotations

import httpx
import pytest
from pydantic import SecretStr

from edge_agent.adapters.gov_catalogue import CatalogueEntryError, GovCatalogueClient
from sentinel_core.config import Settings
from sentinel_core.schemas import CameraStatus, StreamProtocol


def _settings() -> Settings:
    return Settings(gov_access_email="alice@example.com", gov_access_password=SecretStr("s3cret!"))


def _client_with(payload: object, *, status: int = 200) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=payload)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_parses_a_bare_list_response_with_common_field_names() -> None:
    payload = [
        {
            "id": "cam01",
            "name": "Sarkhej Circle",
            "department": "Home Department",
            "lat": 23.0225,
            "lon": 72.5714,
            "codec": "h264",
            "width": 1920,
            "height": 1080,
            "fps": 25,
            "live": True,
        }
    ]
    async with GovCatalogueClient(_settings(), client=_client_with(payload)) as client:
        cameras = await client.fetch()

    assert len(cameras) == 1
    camera = cameras[0]
    assert camera.camera_id == "cam01"
    assert camera.name == "Sarkhej Circle"
    assert camera.department == "Home Department"
    assert camera.location is not None
    assert camera.location.lat == 23.0225
    assert camera.status == CameraStatus.LIVE


async def test_parses_an_enveloped_response() -> None:
    payload = {"cameras": [{"id": "cam02"}]}
    async with GovCatalogueClient(_settings(), client=_client_with(payload)) as client:
        cameras = await client.fetch()

    assert [c.camera_id for c in cameras] == ["cam02"]


@pytest.mark.parametrize("envelope_key", ["items", "data", "results"])
async def test_accepts_any_common_envelope_key(envelope_key: str) -> None:
    payload = {envelope_key: [{"id": "cam03"}]}
    async with GovCatalogueClient(_settings(), client=_client_with(payload)) as client:
        cameras = await client.fetch()

    assert [c.camera_id for c in cameras] == ["cam03"]


async def test_a_malformed_entry_is_skipped_not_fatal() -> None:
    """One camera missing an id must never block onboarding the other 29."""
    payload = [{"id": "cam01"}, {"name": "no id here"}, {"id": "cam03"}]
    async with GovCatalogueClient(_settings(), client=_client_with(payload)) as client:
        cameras = await client.fetch()

    assert [c.camera_id for c in cameras] == ["cam01", "cam03"]


async def test_minimal_entry_with_only_an_id_still_parses() -> None:
    payload = [{"id": "cam09"}]
    async with GovCatalogueClient(_settings(), client=_client_with(payload)) as client:
        cameras = await client.fetch()

    assert cameras[0].camera_id == "cam09"
    assert cameras[0].name == "cam09"  # falls back to the id
    assert cameras[0].location is None


async def test_unrecognised_top_level_shape_raises() -> None:
    async with GovCatalogueClient(_settings(), client=_client_with("not a list or dict")) as client:
        with pytest.raises(CatalogueEntryError):
            await client.fetch()


async def test_camera_ids_are_never_hard_coded_only_catalogue_driven() -> None:
    """The whole point of this client: run it twice with a different
    catalogue and get a different camera set, with no code change."""
    first = _client_with([{"id": "cam01"}])
    second = _client_with([{"id": "cam99"}])

    async with GovCatalogueClient(_settings(), client=first) as client:
        first_ids = [c.camera_id for c in await client.fetch()]
    async with GovCatalogueClient(_settings(), client=second) as client:
        second_ids = [c.camera_id for c in await client.fetch()]

    assert first_ids == ["cam01"]
    assert second_ids == ["cam99"]


async def test_stream_profiles_carry_authenticated_urls_for_each_protocol() -> None:
    payload = [{"id": "cam04"}]
    settings = _settings()
    async with GovCatalogueClient(settings, client=_client_with(payload)) as client:
        cameras = await client.fetch()

    profiles = {p.protocol: p for p in cameras[0].profiles}
    assert StreamProtocol.RTSP in profiles
    assert StreamProtocol.WHEP in profiles
    assert StreamProtocol.HLS in profiles
    assert profiles[StreamProtocol.RTSP].url == settings.gov_stream_url("rtsp", "cam04")
    assert profiles[StreamProtocol.WHEP].url == settings.gov_stream_url("whep", "cam04")
    assert profiles[StreamProtocol.HLS].url == settings.gov_hls_url("cam04")
    # HLS never carries the account credential — only RTSP/WHEP do.
    assert "@" not in profiles[StreamProtocol.HLS].url


async def test_an_externally_owned_client_is_not_closed_by_aclose() -> None:
    """If a caller supplies their own httpx.AsyncClient (e.g. one shared
    across several adapters), this client must not close it out from under
    them."""
    external = _client_with([])
    client = GovCatalogueClient(_settings(), client=external)

    await client.aclose()

    assert not external.is_closed


async def test_http_error_status_propagates() -> None:
    async with GovCatalogueClient(_settings(), client=_client_with({}, status=503)) as client:
        with pytest.raises(httpx.HTTPStatusError):
            await client.fetch()
