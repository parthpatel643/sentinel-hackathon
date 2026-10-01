"""HTTP-level tests for the registry routes the finale depends on: stream
credentials never leaving through operator endpoints, the edge worker's
service-only manifest, device-discovery onboarding, and the audit rows each
onboarding path must leave behind.

Runs the real app against the savepoint-rolled-back `db_session`, so nothing
here persists.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from xml.etree import ElementTree as ET

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core_api.app import app
from core_api.auth.dependencies import current_user, current_user_or_service
from core_api.auth.service import TokenPayload
from core_api.db.base import get_session
from core_api.db.models import AuditLogEntry
from core_api.routers import registry as registry_router
from sentinel_core.config import get_settings
from sentinel_core.drivers.base import DiscoveryScope
from sentinel_core.schemas.camera import CameraDescriptor, StreamProfile, StreamProtocol

SECRET_URL = "rtsp://team%40example.com:s3cr%40t@203.0.113.9:8554/stream/cam06"
ADMIN = TokenPayload(user_id="u-1", email="admin@test.local", role="admin")
OPERATOR = TokenPayload(user_id="u-2", email="operator@test.local", role="operator")


def _as(user: TokenPayload) -> None:
    app.dependency_overrides[current_user] = lambda: user
    app.dependency_overrides[current_user_or_service] = lambda: user


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncIterator[httpx.AsyncClient]:
    async def _session() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_session] = _session
    _as(ADMIN)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


def _service_headers() -> dict[str, str]:
    return {"X-Service-Token": get_settings().edge_service_token.get_secret_value()}


async def _create_camera(client: httpx.AsyncClient, camera_id: str = "fin-cam-01") -> None:
    response = await client.post(
        "/api/v1/cameras",
        json={
            "camera_id": camera_id,
            "name": "Finale junction",
            "department_name": "Police",
            "location": {"lat": 23.03, "lon": 72.58},
            "profiles": [{"protocol": "rtsp", "url": SECRET_URL}],
        },
    )
    assert response.status_code == 201, response.text


async def _audit_actions(db_session: AsyncSession) -> list[str]:
    rows = await db_session.execute(select(AuditLogEntry.action).order_by(AuditLogEntry.seq))
    return list(rows.scalars())


async def test_operator_endpoints_never_return_stream_credentials(
    client: httpx.AsyncClient,
) -> None:
    await _create_camera(client)

    listed = (await client.get("/api/v1/cameras")).json()
    single = (await client.get("/api/v1/cameras/fin-cam-01")).json()

    for camera in (next(c for c in listed if c["camera_id"] == "fin-cam-01"), single):
        url = camera["profiles"][0]["url"]
        assert url == "rtsp://***@203.0.113.9:8554/stream/cam06"
        assert "s3cr" not in url and "team" not in url


async def test_edge_manifest_returns_usable_urls_to_the_service_token_only(
    client: httpx.AsyncClient,
) -> None:
    await _create_camera(client)

    manifest = await client.get("/api/v1/edge/cameras", headers=_service_headers())
    assert manifest.status_code == 200
    camera = next(c for c in manifest.json() if c["camera_id"] == "fin-cam-01")
    assert camera["profiles"][0]["url"] == SECRET_URL

    # A logged-in operator's bearer token is not a service token.
    assert (await client.get("/api/v1/edge/cameras")).status_code == 401
    wrong = await client.get("/api/v1/edge/cameras", headers={"X-Service-Token": "nope"})
    assert wrong.status_code == 401


async def test_manual_and_bulk_onboarding_are_audited(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    await _create_camera(client)
    csv_body = "camera_id,name,url\nfin-cam-02,Second junction,rtsp://10.0.0.2/live\n"
    response = await client.post(
        "/api/v1/cameras/bulk-import",
        params={"dry_run": "false"},
        files={"file": ("cams.csv", csv_body, "text/csv")},
    )
    assert response.json()["succeeded"] == 1

    actions = await _audit_actions(db_session)
    assert "camera_onboarded" in actions
    assert "cameras_bulk_imported" in actions


class _FakeDevice:
    """Stands in for an ONVIF/NVR driver: returns what a real one would,
    including a credentialed stream URL."""

    def __init__(self) -> None:
        self.scope: DiscoveryScope | None = None

    async def discover(self, scope: DiscoveryScope) -> list[CameraDescriptor]:
        self.scope = scope
        return [
            CameraDescriptor(
                camera_id=f"NVR-{channel}",
                name=f"Gate channel {channel}",
                driver_id="hikvision",
                profiles=[
                    StreamProfile(
                        protocol=StreamProtocol.RTSP,
                        url=f"rtsp://admin:p%40ss@10.20.1.15:554/Streaming/Channels/{channel}01",
                    )
                ],
            )
            for channel in (1, 2)
        ]


@pytest.fixture
def fake_device(monkeypatch: pytest.MonkeyPatch) -> _FakeDevice:
    device = _FakeDevice()
    monkeypatch.setattr(registry_router, "_device_source", lambda _request: device)
    return device


def _discovery_body(**overrides: Any) -> dict[str, Any]:
    return {
        "driver": "hikvision",
        "host": "10.20.1.15",
        "username": "admin",
        "password": "p@ss",
        "department_name": "GSRTC",
        "location": {"lat": 23.02, "lon": 72.57},
    } | overrides


async def test_device_discovery_previews_without_writing(
    client: httpx.AsyncClient, fake_device: _FakeDevice
) -> None:
    response = await client.post("/api/v1/cameras/discover-device", json=_discovery_body())

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["dry_run"] is True
    assert [c["camera_id"] for c in body["discovered"]] == ["NVR-1", "NVR-2"]
    assert all("p%40ss" not in u for c in body["discovered"] for u in c["stream_urls"])
    assert body["onboarded"] == []
    assert fake_device.scope is not None and fake_device.scope.host == "10.20.1.15"
    assert (await client.get("/api/v1/cameras/NVR-1")).status_code == 404


async def test_device_discovery_onboards_every_channel_with_operator_metadata(
    client: httpx.AsyncClient, db_session: AsyncSession, fake_device: _FakeDevice
) -> None:
    response = await client.post(
        "/api/v1/cameras/discover-device", json=_discovery_body(dry_run=False)
    )

    assert response.status_code == 200, response.text
    assert sorted(response.json()["onboarded"]) == ["NVR-1", "NVR-2"]
    camera = (await client.get("/api/v1/cameras/NVR-2")).json()
    assert camera["department_name"] == "GSRTC"
    assert camera["location"] == {"lat": 23.02, "lon": 72.57}
    assert camera["source"] == "hikvision_discovery"
    assert "cameras_discovered" in await _audit_actions(db_session)


async def test_device_discovery_is_admin_only(
    client: httpx.AsyncClient, fake_device: _FakeDevice
) -> None:
    _as(OPERATOR)

    response = await client.post("/api/v1/cameras/discover-device", json=_discovery_body())

    assert response.status_code == 403


async def test_an_unreachable_device_is_a_clear_502(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    class _Down:
        async def discover(self, scope: DiscoveryScope) -> list[CameraDescriptor]:
            raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(registry_router, "_device_source", lambda _request: _Down())

    response = await client.post("/api/v1/cameras/discover-device", json=_discovery_body())

    assert response.status_code == 502
    assert "10.20.1.15" in response.json()["detail"]


async def test_lifecycle_report_is_served_as_json_and_as_a_csv_download(
    client: httpx.AsyncClient,
) -> None:
    csv_body = (
        "camera_id,name,department_name,installed_on,maintenance_status\n"
        "lc-http-1,Old pole,Police,2015-01-01,faulty\n"
    )
    await client.post(
        "/api/v1/cameras/bulk-import",
        params={"dry_run": "false"},
        files={"file": ("cams.csv", csv_body, "text/csv")},
    )

    report = await client.get("/api/v1/coverage/lifecycle", params={"department": "Police"})
    assert report.status_code == 200, report.text
    flagged = {c["camera_id"]: c["findings"] for c in report.json()["cameras_needing_attention"]}
    assert flagged["lc-http-1"] == ["ageing", "maintenance"]

    download = await client.get("/api/v1/coverage/lifecycle", params={"format": "csv"})
    assert download.status_code == 200
    assert download.headers["content-type"].startswith("text/csv")
    assert "attachment" in download.headers["content-disposition"]
    assert "lc-http-1" in download.text


async def test_download_filenames_are_readable_by_the_cross_origin_console(
    client: httpx.AsyncClient,
) -> None:
    response = await client.get(
        "/api/v1/coverage/lifecycle",
        params={"format": "csv"},
        headers={"Origin": get_settings().cors_allow_origins[0]},
    )

    exposed = response.headers.get("access-control-expose-headers", "").lower()
    assert "content-disposition" in exposed


async def test_one_bad_camera_does_not_sink_the_batch_or_leak_its_url(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two RTSP profiles on one camera violate the registry's one-per-protocol
    constraint. That camera must fail alone, with an error that does not echo
    the SQL parameters (which carry its credentialed URL)."""

    class _Mixed:
        async def discover(self, scope: DiscoveryScope) -> list[CameraDescriptor]:
            bad = [
                StreamProfile(protocol=StreamProtocol.RTSP, url=f"rtsp://u:s3cret@10.0.0.9/{n}")
                for n in ("main", "sub")
            ]
            good = [StreamProfile(protocol=StreamProtocol.RTSP, url="rtsp://10.0.0.8/main")]
            return [
                CameraDescriptor(camera_id="mix-bad", name="bad", driver_id="onvif", profiles=bad),
                CameraDescriptor(camera_id="mix-good", name="ok", driver_id="onvif", profiles=good),
            ]

    monkeypatch.setattr(registry_router, "_device_source", lambda _request: _Mixed())

    response = await client.post(
        "/api/v1/cameras/discover-device", json=_discovery_body(dry_run=False)
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["onboarded"] == ["mix-good"]
    assert [f["camera_id"] for f in body["failed"]] == ["mix-bad"]
    assert "s3cret" not in body["failed"][0]["error"]


async def test_a_device_answering_with_html_is_a_clear_502(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    class _WebPage:
        async def discover(self, scope: DiscoveryScope) -> list[CameraDescriptor]:
            ET.fromstring("<html><body>Login</body")
            return []

    monkeypatch.setattr(registry_router, "_device_source", lambda _request: _WebPage())

    response = await client.post("/api/v1/cameras/discover-device", json=_discovery_body())

    assert response.status_code == 502


async def test_heartbeat_reports_analysis_lag_and_silence_turns_live_into_stale(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import update

    from core_api.db.models import Camera

    await _create_camera(client)
    behind = datetime.now(UTC) - timedelta(seconds=12)
    beat = await client.patch(
        "/api/v1/cameras/fin-cam-01/health",
        headers=_service_headers(),
        json={"status": "live", "analysed_fps": 8.1, "stream_position_at": behind.isoformat()},
    )
    assert beat.status_code == 200, beat.text
    camera = beat.json()
    assert camera["status"] == "live"
    assert camera["analysed_fps"] == 8.1
    assert 11.0 <= camera["analysis_lag_s"] <= 20.0

    counted = await client.patch(
        "/api/v1/cameras/fin-cam-01/health",
        headers=_service_headers(),
        json={"status": "live", "people_in_view": 7, "vehicles_in_view": 3},
    )
    assert (counted.json()["people_in_view"], counted.json()["vehicles_in_view"]) == (7, 3)

    # The worker dies: no more heartbeats.
    await db_session.execute(
        update(Camera)
        .where(Camera.camera_id == "fin-cam-01")
        .values(last_seen_at=datetime.now(UTC) - timedelta(minutes=2))
    )
    assert (await client.get("/api/v1/cameras/fin-cam-01")).json()["status"] == "stale"


async def test_only_administrators_change_the_registry(client: httpx.AsyncClient) -> None:
    _as(OPERATOR)
    csv_body = "camera_id,name\nop-cam,Operator camera\n"

    create = await client.post("/api/v1/cameras", json={"camera_id": "op-cam", "name": "x"})
    preview = await client.post(
        "/api/v1/cameras/bulk-import",
        params={"dry_run": "true"},
        files={"file": ("c.csv", csv_body, "text/csv")},
    )
    commit = await client.post(
        "/api/v1/cameras/bulk-import",
        params={"dry_run": "false"},
        files={"file": ("c.csv", csv_body, "text/csv")},
    )
    sync = await client.post("/api/v1/cameras/discover")

    assert create.status_code == 403
    assert preview.status_code == 200
    assert commit.status_code == 403
    assert sync.status_code == 403


async def test_the_edge_worker_still_registers_its_cameras(client: httpx.AsyncClient) -> None:
    app.dependency_overrides.pop(current_user_or_service, None)

    response = await client.post(
        "/api/v1/cameras",
        headers=_service_headers(),
        json={"camera_id": "worker-cam", "name": "Catalogue camera"},
    )

    assert response.status_code == 201, response.text


async def _create_private_camera(
    client: httpx.AsyncClient, camera_id: str, attributes: dict[str, str]
) -> httpx.Response:
    return await client.post(
        "/api/v1/cameras",
        json={
            "camera_id": camera_id,
            "name": "Society gate",
            "department_name": "Police",
            "tier": "d_registry_only",
            "profiles": [{"protocol": "rtsp", "url": SECRET_URL}],
            "attributes": {"ownership": "private", **attributes},
        },
    )


async def test_a_private_camera_without_current_consent_is_not_served(
    client: httpx.AsyncClient,
) -> None:
    current = {"consent_ref": "SOC/2026/0141", "consent_expires_on": "2099-01-01"}
    assert (await _create_private_camera(client, "pvt-ok", current)).status_code == 201
    lapsed = {"consent_ref": "SOC/2024/0007", "consent_expires_on": "2025-01-01"}
    assert (await _create_private_camera(client, "pvt-lapsed", lapsed)).status_code == 201
    assert (await _create_private_camera(client, "pvt-none", {})).status_code == 201

    manifest = (await client.get("/api/v1/edge/cameras", headers=_service_headers())).json()
    served = {c["camera_id"] for c in manifest}
    assert "pvt-ok" in served
    assert not served & {"pvt-lapsed", "pvt-none"}

    stream = (await client.get("/api/v1/cameras/pvt-lapsed/stream")).json()
    assert stream["available"] is False
    assert "consent" in stream["reason"]
    # Still in the registry, so the station can see it and renew consent.
    assert (await client.get("/api/v1/cameras/pvt-lapsed")).status_code == 200


async def test_manual_onboarding_validates_consent_attributes(
    client: httpx.AsyncClient,
) -> None:
    response = await _create_private_camera(
        client, "pvt-bad", {"consent_ref": "X", "consent_expires_on": "31/12/2026"}
    )

    assert response.status_code == 422
    assert "YYYY-MM-DD" in response.text
