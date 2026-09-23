"""End-to-end proof that department-tenancy Postgres RLS (docs/08-SECURITY-
HARDENING.md, migration 23c60ee4c006) genuinely isolates data across
departments — through the REAL FastAPI app (httpx's ASGITransport, not a
mocked service layer), so the whole chain is exercised: login -> JWT with a
department_id claim -> TenancyMiddleware -> get_session's `SET LOCAL` ->
the RLS policies on cameras/detections/alerts.

This creates and commits real rows (visible across connections, unlike the
savepoint-rollback `db_session` fixture used elsewhere) because the RLS
policies must be exercised by the app's OWN connection pool (running as the
non-superuser `sentinel_app` role), not the test's. Cleaned up in a
fixture-teardown `finally`, following this project's established
test-data-hygiene pattern for cross-connection-visible data.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from core_api.app import create_app
from core_api.db.base import get_engine, get_sessionmaker
from core_api.db.models import Department

pytestmark = pytest.mark.usefixtures("_require_postgres")


@pytest_asyncio.fixture(autouse=True)
async def _fresh_engine_per_test() -> AsyncIterator[None]:
    """`core_api.db.base.get_engine()`/`get_sessionmaker()` are process-wide
    `@lru_cache`d — fine for the real app (one event loop, one process),
    but pytest-asyncio gives each test function its own event loop by
    default, and an asyncpg connection pool bound to one loop breaks with
    'another operation is in progress' once a later test's loop touches it
    (the exact issue services/core_api/tests/conftest.py's own db_session
    fixture already works around by never using this cache). Clearing the
    cache before and after each test forces a fresh engine bound to
    *this* test's loop, since this test module exercises the real app
    end-to-end (not a hand-rolled per-test engine like conftest.py's)."""
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()
    yield
    await get_engine().dispose()
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()


@pytest_asyncio.fixture
async def _require_postgres(db_session: AsyncSession) -> None:
    """Piggybacks on the existing db_session fixture purely for its
    Postgres-reachability skip behaviour — this test suite needs a real
    server either way."""


@pytest_asyncio.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# Deliberately NOT the seeded admin. Depending on that account's documented
# default password coupled the suite to a deployment's credentials: rotating
# it before exposing an instance publicly — which is exactly what you must do
# — made these four tests fail with 401. The suite now mints its own
# short-lived admin instead, so credential hygiene and the test suite stop
# fighting each other.
ADMIN_PASSWORD = "rls-test-admin-password-123"


@pytest_asyncio.fixture
async def admin_credentials() -> AsyncIterator[str]:
    """An admin created directly in the database, the same way the seed
    script bootstraps the first one — there is no API to create an admin
    without already holding an admin token."""
    from core_api.auth.service import hash_password
    from core_api.db.models import User

    email = f"rls-test-admin-{uuid.uuid4().hex[:8]}@sentinel-platform.example"
    session_factory = get_sessionmaker()
    async with session_factory() as session:
        session.add(
            User(
                email=email,
                hashed_password=hash_password(ADMIN_PASSWORD),
                full_name="RLS Test Admin",
                role="admin",
            )
        )
        await session.commit()
    try:
        yield email
    finally:
        async with session_factory() as session:
            user = (
                await session.execute(select(User).where(User.email == email))
            ).scalar_one_or_none()
            if user is not None:
                await session.delete(user)
                await session.commit()


async def _login(client: httpx.AsyncClient, email: str, password: str) -> str:
    resp = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    resp.raise_for_status()
    token: str = resp.json()["access_token"]
    return token


@pytest_asyncio.fixture
async def tenancy_fixture(
    client: httpx.AsyncClient, admin_credentials: str
) -> AsyncIterator[dict[str, str]]:
    """Two departments, one camera each, one operator user scoped to each
    department. Real commits, real cleanup."""
    suffix = uuid.uuid4().hex[:8]
    admin_token = await _login(client, admin_credentials, ADMIN_PASSWORD)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    dept_a_name = f"RLS Test Alpha {suffix}"
    dept_b_name = f"RLS Test Beta {suffix}"
    cam_a = f"rls-test-cam-a-{suffix}"
    cam_b = f"rls-test-cam-b-{suffix}"

    for camera_id, dept_name in ((cam_a, dept_a_name), (cam_b, dept_b_name)):
        resp = await client.post(
            "/api/v1/cameras",
            json={
                "camera_id": camera_id,
                "name": f"Camera {camera_id}",
                "driver_id": "rtsp",
                "department_name": dept_name,
                "tier": "a_continuous",
            },
            headers={"X-Service-Token": "dev-only-edge-service-token"},
        )
        resp.raise_for_status()

    depts_resp = await client.get("/api/v1/cameras", headers=admin_headers)
    depts_resp.raise_for_status()
    cameras_by_id = {c["camera_id"]: c for c in depts_resp.json()}

    # Departments are looked up by name via a raw query — there's no public
    # "list departments" endpoint yet, and this test only needs the UUID.
    async with get_sessionmaker()() as session:
        dept_a_id = (
            await session.execute(select(Department.id).where(Department.name == dept_a_name))
        ).scalar_one()
        dept_b_id = (
            await session.execute(select(Department.id).where(Department.name == dept_b_name))
        ).scalar_one()

    user_a_email = f"rls-test-user-a-{suffix}@example.com"
    user_b_email = f"rls-test-user-b-{suffix}@example.com"
    for email, dept_id in ((user_a_email, dept_a_id), (user_b_email, dept_b_id)):
        resp = await client.post(
            "/api/v1/auth/users",
            json={
                "email": email,
                "password": "rls-test-password-123",
                "full_name": "RLS Test User",
                "role": "operator",
                "department_id": str(dept_id),
            },
            headers=admin_headers,
        )
        resp.raise_for_status()

    assert cam_a in cameras_by_id and cam_b in cameras_by_id

    try:
        yield {
            "cam_a": cam_a,
            "cam_b": cam_b,
            "user_a_email": user_a_email,
            "user_b_email": user_b_email,
        }
    finally:
        async with get_sessionmaker()() as session:
            await session.execute(
                text("DELETE FROM users WHERE email IN (:a, :b)"),
                {"a": user_a_email, "b": user_b_email},
            )
            await session.execute(
                text("DELETE FROM cameras WHERE camera_id IN (:a, :b)"),
                {"a": cam_a, "b": cam_b},
            )
            await session.execute(
                text("DELETE FROM departments WHERE name IN (:a, :b)"),
                {"a": dept_a_name, "b": dept_b_name},
            )
            await session.commit()
            # Deliberately NOT deleting the audit_log rows this test's user
            # creation left behind: deleting a row from the *middle* of a
            # hash chain breaks the chain for every row after it forever —
            # exactly the tamper-detection behaviour the chain exists to
            # have. Test-created audit entries are real audit entries (the
            # actions genuinely happened); the dev-DB-wide `DELETE FROM
            # audit_log` this session already runs before `make check`
            # (alongside detections/cameras/etc.) is the right place to
            # reset the chain to empty between clean test runs, not a
            # per-test partial delete here.


async def test_a_department_scoped_user_only_sees_their_own_camera(
    client: httpx.AsyncClient, tenancy_fixture: dict[str, str]
) -> None:
    token_a = await _login(client, tenancy_fixture["user_a_email"], "rls-test-password-123")

    resp = await client.get("/api/v1/cameras", headers={"Authorization": f"Bearer {token_a}"})
    resp.raise_for_status()
    visible_ids = {c["camera_id"] for c in resp.json()}

    assert tenancy_fixture["cam_a"] in visible_ids
    assert tenancy_fixture["cam_b"] not in visible_ids


async def test_the_other_departments_user_only_sees_their_own_camera(
    client: httpx.AsyncClient, tenancy_fixture: dict[str, str]
) -> None:
    token_b = await _login(client, tenancy_fixture["user_b_email"], "rls-test-password-123")

    resp = await client.get("/api/v1/cameras", headers={"Authorization": f"Bearer {token_b}"})
    resp.raise_for_status()
    visible_ids = {c["camera_id"] for c in resp.json()}

    assert tenancy_fixture["cam_b"] in visible_ids
    assert tenancy_fixture["cam_a"] not in visible_ids


async def test_an_unscoped_admin_sees_both_departments_cameras(
    client: httpx.AsyncClient, tenancy_fixture: dict[str, str], admin_credentials: str
) -> None:
    """An admin account has no department_id (NULL) — the RLS
    policy's documented meaning of NULL is "unrestricted," not "sees
    nothing," which is what makes it safe to turn on without breaking every
    existing HQ/admin workflow."""
    admin_token = await _login(client, admin_credentials, ADMIN_PASSWORD)

    resp = await client.get("/api/v1/cameras", headers={"Authorization": f"Bearer {admin_token}"})
    resp.raise_for_status()
    visible_ids = {c["camera_id"] for c in resp.json()}

    assert tenancy_fixture["cam_a"] in visible_ids
    assert tenancy_fixture["cam_b"] in visible_ids


async def test_a_direct_camera_fetch_of_the_other_departments_camera_404s(
    client: httpx.AsyncClient, tenancy_fixture: dict[str, str]
) -> None:
    """RLS hides the row entirely — a scoped user asking for the other
    department's camera by ID sees "not found," not "forbidden" (Postgres
    RLS is a WHERE-clause filter, indistinguishable at the SQL layer from
    the row never having existed, which is the correct behaviour: it
    doesn't even confirm the camera_id exists)."""
    token_a = await _login(client, tenancy_fixture["user_a_email"], "rls-test-password-123")

    resp = await client.get(
        f"/api/v1/cameras/{tenancy_fixture['cam_b']}",
        headers={"Authorization": f"Bearer {token_a}"},
    )

    assert resp.status_code == 404
