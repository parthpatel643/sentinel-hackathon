"""Find out why the camera feed is not coming.

Live preview depends on a chain: Docker, Postgres, the relay, the API, gov
credentials, an onboarded camera, the vehicle model, a running worker, a
registered relay path, and finally HLS. A break anywhere in that chain shows
up in the browser as the same thing — a tile that says "Connecting..." — so
the useful question is never "is it broken" but "which link".

This walks the chain in dependency order and stops at the first break, because
everything after a broken link fails for reasons that are not its own fault
and reporting those too would bury the one that matters.

    uv run python scripts/diagnose.py            # local stack
    uv run python scripts/diagnose.py --gov      # also check the government grid

Exits non-zero when something is wrong, so it can gate a demo.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import httpx

from sentinel_core.config import Settings

REPO_ROOT = Path(__file__).resolve().parents[1]
VEHICLE_MODEL = REPO_ROOT / "models" / "weights" / "yolo11n.onnx"

GREEN, RED, YELLOW, DIM, RESET = "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m"


@dataclass
class Result:
    ok: bool
    detail: str
    remedy: str = ""
    # A warning is reported but does not stop the walk: the chain can still
    # work without it, so hiding what comes next would be unhelpful.
    warning: bool = False


def _ok(detail: str) -> Result:
    return Result(True, detail)


def _fail(detail: str, remedy: str) -> Result:
    return Result(False, detail, remedy)


def _warn(detail: str, remedy: str) -> Result:
    return Result(False, detail, remedy, warning=True)


def check_docker() -> Result:
    if shutil.which("docker") is None:
        return _fail("docker is not installed", "Install Docker Desktop or OrbStack.")
    probe = subprocess.run(
        ["docker", "ps", "--format", "{{.Names}}"], capture_output=True, text=True
    )
    if probe.returncode != 0:
        return _fail(
            "the docker daemon is not responding",
            "Start Docker Desktop, or `orb start` for OrbStack. A laptop that slept "
            "is enough to stop it.",
        )
    names = {n for n in probe.stdout.split() if n.startswith("sentinel-")}
    expected = {"sentinel-postgres", "sentinel-mediamtx"}
    if missing := expected - names:
        return _fail(
            f"containers not running: {', '.join(sorted(missing))}",
            "Run `make up`, then `make ps` until they report healthy.",
        )
    return _ok(f"{len(names)} sentinel containers up")


async def check_relay(settings: Settings, client: httpx.AsyncClient) -> Result:
    base = settings.relay_api_url.rstrip("/")
    try:
        response = await client.get(f"{base}/v3/config/paths/list")
    except httpx.HTTPError as exc:
        return _fail(
            f"cannot reach the relay API at {base}: {type(exc).__name__}",
            "The mediamtx container is not up or not publishing :9997. `make up`.",
        )
    if response.status_code != 200:
        return _fail(
            f"relay API returned HTTP {response.status_code}",
            "Check `docker logs sentinel-mediamtx`.",
        )
    return _ok(f"relay API healthy ({response.json().get('itemCount', 0)} paths configured)")


async def check_api(settings: Settings, client: httpx.AsyncClient) -> Result:
    base = settings.core_api_url.rstrip("/")
    try:
        response = await client.get(f"{base}/api/v1/health")
    except httpx.HTTPError as exc:
        return _fail(
            f"cannot reach the core API at {base}: {type(exc).__name__}",
            "Start it with `make api`. Nothing else works until this does.",
        )
    if response.status_code != 200:
        return _fail(f"core API returned HTTP {response.status_code}", "Check the `make api` log.")
    return _ok(f"core API healthy ({response.json().get('environment', '?')})")


def check_model() -> Result:
    if not VEHICLE_MODEL.exists():
        return _fail(
            "the vehicle model is missing",
            "A fresh clone has no weights — models/weights/ is gitignored. Run:\n"
            "      uv run --isolated --with ultralytics --with onnx "
            "python scripts/export_models.py",
        )
    return _ok(f"vehicle model present ({VEHICLE_MODEL.stat().st_size / 1e6:.1f} MB)")


def check_gov_credentials(settings: Settings) -> Result:
    email = settings.gov_access_email
    password = settings.gov_access_password
    if not email or not (password and password.get_secret_value()):
        return _fail(
            "no government grid credentials",
            "Copy .env.example to .env and fill in SENTINEL_GOV_ACCESS_EMAIL and "
            "SENTINEL_GOV_ACCESS_PASSWORD. Only approved emails can connect.",
        )
    return _ok(f"credentials present for {email}")


async def check_gov_catalogue() -> Result:
    from sentinel_core.gov_catalogue import GovCatalogueClient

    try:
        cameras = await GovCatalogueClient(Settings()).fetch()
    except Exception as exc:  # any failure here is worth reporting verbatim
        message = str(exc)
        if "403" in message:
            return _fail(
                "the catalogue returned 403 — the viewing quota is exhausted",
                "Stop every worker and wait 15-20 minutes. Reducing the camera count is "
                "not enough; consumption has to reach zero. Note the quota is per "
                "ACCOUNT, so another machine using the same credentials also spends it.",
            )
        if "401" in message:
            return _fail(
                "the catalogue rejected the credentials (401)",
                "Check SENTINEL_GOV_ACCESS_EMAIL/PASSWORD in .env.",
            )
        return _fail(f"catalogue unreachable: {message[:90]}", "Check network access.")
    return _ok(f"catalogue reachable ({len(cameras)} cameras)")


async def check_cameras_onboarded(settings: Settings, client: httpx.AsyncClient) -> Result:
    base = settings.core_api_url.rstrip("/")
    # The registry is a human-facing endpoint and wants a real login, not the
    # machine-to-machine service token the worker uses for ingest.
    email = os.environ.get("SENTINEL_ADMIN_EMAIL", "admin@sentinel-platform.com")
    password = os.environ.get("SENTINEL_ADMIN_PASSWORD", "sentinel-admin-2026")
    # Retried once because the first request after Postgres restarts spends the
    # connection pool's now-dead connection and fails, while the next one
    # reconnects — a diagnostic that reports that single 500 as a broken login
    # sends you looking at credentials when nothing is wrong with them.
    login = None
    for attempt in range(2):
        try:
            login = await client.post(
                f"{base}/api/v1/auth/login", json={"email": email, "password": password}
            )
        except httpx.HTTPError as exc:
            return _fail(
                f"could not reach the login endpoint: {type(exc).__name__}", "Is the API up?"
            )
        if login.status_code == 200:
            break
        if attempt == 0:
            await asyncio.sleep(1.0)
    assert login is not None
    if login.status_code != 200:
        return _warn(
            f"could not log in as {email} (HTTP {login.status_code})",
            "Run `make seed`, or set SENTINEL_ADMIN_PASSWORD if you rotated it. The "
            "registry itself may be fine — this check just cannot see it.",
        )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    try:
        response = await client.get(f"{base}/api/v1/cameras?limit=200", headers=headers)
    except httpx.HTTPError as exc:
        return _fail(f"could not list cameras: {type(exc).__name__}", "Is `make api` running?")
    if response.status_code != 200:
        return _warn(f"could not list cameras (HTTP {response.status_code})", "")
    payload = response.json()
    cameras = payload if isinstance(payload, list) else payload.get("items", [])
    if not cameras:
        return _fail(
            "no cameras are onboarded",
            "The registry is empty, so there is nothing to show. For the government "
            "grid, POST /api/v1/cameras/discover. For the synthetic grid, run "
            "`uv run python scripts/synthetic_grid.py all`.",
        )
    live = [c for c in cameras if c.get("status") == "live"]
    if not live:
        return _warn(
            f"{len(cameras)} cameras onboarded, none currently live",
            "Expected if no worker is running — the next check covers that.",
        )
    return _ok(f"{len(cameras)} onboarded, {len(live)} live")


def check_worker_running() -> Result:
    probe = subprocess.run(["ps", "-eo", "command"], capture_output=True, text=True)
    running = [ln for ln in probe.stdout.splitlines() if "edge_agent.worker" in ln]
    if not running:
        return _fail(
            "no edge worker is running",
            "Nothing is pulling any camera, so no feed can arrive. Start one:\n"
            "      make worker                                    # synthetic grid\n"
            "      make worker SOURCE=gov CAMERAS=cam06,cam30 STRIDE=3",
        )
    return _ok(f"{len(running)} worker process(es) running")


async def check_relay_paths(settings: Settings, client: httpx.AsyncClient) -> Result:
    base = settings.relay_api_url.rstrip("/")
    try:
        items = (await client.get(f"{base}/v3/paths/list")).json().get("items", [])
    except httpx.HTTPError as exc:
        return _fail(f"could not list relay paths: {type(exc).__name__}", "Is the relay up?")
    if not items:
        return _fail(
            "the relay has no paths at all",
            "The worker registers these at startup. If it is running, it may have "
            "failed to reach the relay — check its log for 'could not register relay path'.",
        )
    ready = [i["name"] for i in items if i.get("ready")]
    if not ready:
        return _fail(
            f"{len(items)} relay paths exist but none are carrying video",
            "The relay cannot pull from the cameras. Usually the viewing quota (403/401 "
            "upstream) or credentials. Check `docker logs sentinel-mediamtx`.",
        )
    return _ok(f"{len(ready)} of {len(items)} paths carrying video: {', '.join(ready[:4])}")


async def check_hls(settings: Settings, client: httpx.AsyncClient) -> Result:
    base = settings.relay_api_url.rstrip("/")
    items = (await client.get(f"{base}/v3/paths/list")).json().get("items", [])
    ready = [i["name"] for i in items if i.get("ready")]
    if not ready:
        return _warn("no ready path to test HLS against", "Fix the previous check first.")

    serving, failing = [], []
    for name in ready[:6]:
        url = f"{settings.relay_hls_url.rstrip('/')}/{name}/index.m3u8"
        try:
            response = await client.get(url, follow_redirects=True)
            (serving if response.status_code == 200 else failing).append(
                f"{name}({response.status_code})"
            )
        except httpx.HTTPError:
            failing.append(f"{name}(unreachable)")

    if not serving:
        return _fail(
            f"no camera is serving HLS: {', '.join(failing)}",
            "Paths carry video but the muxer will not produce a playlist. Most often "
            "packet loss starving it of keyframes, or the machine being saturated — "
            "try fewer cameras and --frame-stride 3.",
        )
    if failing:
        return _warn(
            f"serving: {', '.join(serving)} | not yet: {', '.join(failing)}",
            "Partial is normal — a camera short of a keyframe recovers by itself.",
        )
    return _ok(f"HLS serving for {', '.join(serving)}")


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--gov", action="store_true", help="also check the government grid credentials and quota"
    )
    args = parser.parse_args()
    settings = Settings()

    print(f"\n{DIM}Walking the live-preview chain; stopping at the first break.{RESET}\n")

    async with httpx.AsyncClient(timeout=20.0) as client:
        checks: list[tuple[str, object]] = [
            ("docker stack", check_docker()),
            ("media relay", await check_relay(settings, client)),
            ("core API", await check_api(settings, client)),
            ("vehicle model", check_model()),
        ]
        if args.gov:
            checks.append(("gov credentials", check_gov_credentials(settings)))

        failed = False
        for label, result in checks:
            assert isinstance(result, Result)
            failed = _report(label, result) or failed
            if failed:
                return _finish(failed)

        if args.gov and _report("gov catalogue", await check_gov_catalogue()):
            return _finish(True)

        for label, result in (
            ("camera registry", await check_cameras_onboarded(settings, client)),
            ("edge worker", check_worker_running()),
            ("relay paths", await check_relay_paths(settings, client)),
            ("HLS playback", await check_hls(settings, client)),
        ):
            if _report(label, result):
                return _finish(True)

    return _finish(False)


def _report(label: str, result: Result) -> bool:
    """Print one line; returns True if this break should stop the walk."""
    if result.ok:
        print(f"  {GREEN}✓{RESET} {label:<18} {result.detail}")
        return False
    mark, colour = ("!", YELLOW) if result.warning else ("✗", RED)
    print(f"  {colour}{mark}{RESET} {label:<18} {result.detail}")
    if result.remedy:
        print(f"      {DIM}{result.remedy}{RESET}")
    return not result.warning


def _finish(failed: bool) -> int:
    if failed:
        print(f"\n{RED}Stopped at the first break.{RESET} Fix the above and run this again.\n")
        return 1
    print(f"\n{GREEN}The whole chain is healthy.{RESET} If the browser still shows nothing,")
    print(f"{DIM}  it is the console reaching the API, not the API itself — look in the{RESET}")
    print(f"{DIM}  browser console for CORS errors; GETTING-STARTED.md section 7.{RESET}\n")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
