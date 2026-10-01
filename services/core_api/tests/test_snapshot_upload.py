"""A worker on another machine uploads the evidence frames it wrote."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
import pytest_asyncio

from core_api.app import app
from core_api.routers import detections as detections_router
from sentinel_core.config import Settings, get_settings

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64


@pytest_asyncio.fixture
async def client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[httpx.AsyncClient]:
    settings = Settings(
        snapshots_dir=str(tmp_path / "blurred"),
        snapshot_originals_dir=str(tmp_path / "originals"),
    )
    monkeypatch.setattr(detections_router, "get_settings", lambda: settings)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def _written(root: Path) -> list[Path]:
    return list(root.rglob("*.jpg"))


def _svc() -> dict[str, str]:
    return {"X-Service-Token": get_settings().edge_service_token.get_secret_value()}


async def test_uploaded_frames_land_where_the_api_serves_them(
    client: httpx.AsyncClient, tmp_path: Path
) -> None:
    response = await client.put(
        "/api/v1/detections/01JUPLOAD00000000000000001/snapshot",
        headers=_svc(),
        files={"blurred": ("b.jpg", JPEG, "image/jpeg"), "original": ("o.jpg", JPEG, "image/jpeg")},
    )

    assert response.status_code == 204, response.text
    assert (tmp_path / "blurred" / "01JUPLOAD00000000000000001.jpg").read_bytes() == JPEG
    assert (tmp_path / "originals" / "01JUPLOAD00000000000000001.jpg").read_bytes() == JPEG


@pytest.mark.parametrize("event_id", ["..%2F..%2Fetc", "a.b", "x" * 65])
async def test_an_event_id_cannot_choose_where_a_file_is_written(
    client: httpx.AsyncClient, tmp_path: Path, event_id: str
) -> None:
    response = await client.put(
        f"/api/v1/detections/{event_id}/snapshot",
        headers=_svc(),
        files={"blurred": ("b.jpg", JPEG, "image/jpeg")},
    )

    assert response.status_code in (404, 422)
    assert not _written(tmp_path)


async def test_only_jpegs_and_only_the_service_token(client: httpx.AsyncClient) -> None:
    not_jpeg = await client.put(
        "/api/v1/detections/01JUPLOAD2/snapshot",
        headers=_svc(),
        files={"blurred": ("b.jpg", b"<html>", "image/jpeg")},
    )
    no_token = await client.put(
        "/api/v1/detections/01JUPLOAD2/snapshot",
        files={"blurred": ("b.jpg", JPEG, "image/jpeg")},
    )

    assert not_jpeg.status_code == 415
    assert no_token.status_code == 401
