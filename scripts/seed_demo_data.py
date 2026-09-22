#!/usr/bin/env python3
"""Seed realistic demo data into a running core_api so the Operator Console
has something to show immediately — cameras with varied health, a
multi-camera vehicle route, and an armed BOLO with a retro-scan hit (the
flagship "BOLO moment", 00-SOLUTION-PLAN.md section 1.1).

Deliberately NOT run as part of the test suite or CI: the integration tests
in services/core_api/tests/ assert exact counts against a near-empty
database (test_no_cameras_yields_an_empty_report, test_list_alerts_filters_by_status,
etc.) and would fail if this data were left sitting in the same dev Postgres
instance they query. Run this only when you want to look at the UI, and
expect `make check` / pytest to need a clean database again afterwards (see
this script's own `--reset` flag).

Usage:
    uv run python scripts/seed_demo_data.py            # seed
    uv run python scripts/seed_demo_data.py --reset     # wipe demo tables only
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime, timedelta

import httpx

API_BASE = "http://localhost:18000"

CAMERAS = [
    {
        "camera_id": "ahm-sarkhej-01",
        "name": "Sarkhej Circle North",
        "site_name": "Sarkhej Circle",
        "location": {"lat": 23.0106, "lon": 72.5040},
        "tier": "a_continuous",
        "health": {
            "status": "live",
            "measured_fps": 14.8,
            "declared_fps": 15.0,
            "reconnects": 0,
            "discontinuities": 0,
        },
    },
    {
        "camera_id": "ahm-sghighway-02",
        "name": "SG Highway Gate 2",
        "site_name": "SG Highway",
        "location": {"lat": 23.0395, "lon": 72.5066},
        "tier": "a_continuous",
        "health": {
            "status": "live",
            "measured_fps": 14.5,
            "declared_fps": 15.0,
            "reconnects": 1,
            "discontinuities": 0,
        },
    },
    {
        "camera_id": "ahm-iscon-03",
        "name": "Iskcon Crossroad",
        "site_name": "Iskcon Crossroad",
        "location": {"lat": 23.0270, "lon": 72.5075},
        "tier": "b_sampled",
        "health": {
            "status": "degraded",
            "measured_fps": 6.2,
            "declared_fps": 15.0,
            "reconnects": 4,
            "discontinuities": 2,
        },
    },
    {
        "camera_id": "ahm-prahlad-04",
        "name": "Prahladnagar Junction",
        "site_name": "Prahladnagar",
        "location": {"lat": 23.0125, "lon": 72.5000},
        "tier": "b_sampled",
        "health": {
            "status": "down",
            "measured_fps": 0,
            "declared_fps": 15.0,
            "reconnects": 9,
            "discontinuities": 1,
        },
    },
]

DEPARTMENT_NAME = "Ahmedabad City Police"


def _iso(minutes_ago: float) -> str:
    return (datetime.now(UTC) - timedelta(minutes=minutes_ago)).isoformat()


DETECTIONS = [
    {
        "event_id": "01JDEMO0000000000000001",
        "camera_id": "ahm-sarkhej-01",
        "plate_text": "GJ01AB1234",
        "plate_normalised": "GJ01AB1234",
        "plate_ambiguity_key": "6J01481234",
        "plate_confidence": 0.96,
        "vehicle_class": "car",
        "pts_ms": 1000,
        "observed_at": _iso(120),
    },
    {
        "event_id": "01JDEMO0000000000000002",
        "camera_id": "ahm-sghighway-02",
        "plate_text": "GJ01AB1234",
        "plate_normalised": "GJ01AB1234",
        "plate_ambiguity_key": "6J01481234",
        "plate_confidence": 0.94,
        "vehicle_class": "car",
        "pts_ms": 2000,
        "observed_at": _iso(100),
    },
    {
        "event_id": "01JDEMO0000000000000003",
        "camera_id": "ahm-iscon-03",
        "plate_text": "GJ014B1234",
        "plate_normalised": "GJ014B1234",
        "plate_ambiguity_key": "6J01481234",
        "plate_confidence": 0.71,
        "vehicle_class": "car",
        "pts_ms": 3000,
        "observed_at": _iso(57),
    },
    {
        "event_id": "01JDEMO0000000000000004",
        "camera_id": "ahm-prahlad-04",
        "plate_text": "GJ01AB1234",
        "plate_normalised": "GJ01AB1234",
        "plate_ambiguity_key": "6J01481234",
        "plate_confidence": 0.93,
        "vehicle_class": "car",
        "pts_ms": 4000,
        "observed_at": _iso(25),
    },
    {
        "event_id": "01JDEMO0000000000000005",
        "camera_id": "ahm-sghighway-02",
        "plate_text": "GJ05CD9999",
        "plate_normalised": "GJ05CD9999",
        "plate_ambiguity_key": "6J05CD9999",
        "plate_confidence": 0.89,
        "vehicle_class": "motorcycle",
        "pts_ms": 5000,
        "observed_at": _iso(12),
    },
]

BOLOS = [
    {
        "plate": "GJ01AB1234",
        "entry_type": "stolen_vehicle",
        "priority": "critical",
        "case_reference": "FIR-2026-0417",
        "requested_by": "Insp. R. Shah",
        "notes": "Reported stolen from Sarkhej, 22 Sep",
    },
    {
        "plate": "GJ05CD9999",
        "entry_type": "wanted_vehicle",
        "priority": "high",
        "case_reference": "CR-2026-0891",
        "requested_by": "SI P. Patel",
        "notes": "Wanted in connection with a hit-and-run",
    },
]


def seed() -> None:
    with httpx.Client(base_url=API_BASE, timeout=10.0) as client:
        for cam in CAMERAS:
            response = client.post(
                "/api/v1/cameras",
                json={
                    "camera_id": cam["camera_id"],
                    "name": cam["name"],
                    "driver_id": "rtsp_generic",
                    "department_name": DEPARTMENT_NAME,
                    "site_name": cam["site_name"],
                    "location": cam["location"],
                    "tier": cam["tier"],
                    "attributes": {},
                    "profiles": [],
                },
            )
            if response.status_code not in (201, 409):
                response.raise_for_status()

        for detection in DETECTIONS:
            response = client.post(
                "/api/v1/detections", json={**detection, "node_id": "edge-local-01"}
            )
            response.raise_for_status()

        for bolo in BOLOS:
            response = client.post("/api/v1/bolo", json=bolo)
            response.raise_for_status()
            result = response.json()
            print(
                f"BOLO armed for {bolo['plate']}: {result['retro_alerts_created']} alert(s), "
                f"{result['retro_sightings_found']} sighting(s) found on file"
            )

        # Health PATCH last: detection ingest opportunistically marks a
        # camera 'live' as proof of activity (see
        # core_api/detections/service.py), which would otherwise overwrite
        # the "down"/"degraded" demo variety just seeded above.
        for cam in CAMERAS:
            response = client.patch(
                f"/api/v1/cameras/{cam['camera_id']}/health", json=cam["health"]
            )
            response.raise_for_status()

    print(f"\nseeded {len(CAMERAS)} cameras, {len(DETECTIONS)} detections, {len(BOLOS)} BOLOs.")
    print("Open the Operator Console and try: Find a Vehicle -> GJ01AB1234")


def reset() -> None:
    """Deletes only the demo rows this script created (by camera_id/plate),
    not a blanket TRUNCATE — safe to run against a database that also has
    real catalogue-driven cameras in it."""
    import subprocess

    camera_ids = ",".join(f"'{c['camera_id']}'" for c in CAMERAS)
    sql = f"""
    DELETE FROM alerts WHERE camera_id IN ({camera_ids});
    DELETE FROM watchlist_entries WHERE plate_normalised IN ('GJ01AB1234', 'GJ05CD9999');
    DELETE FROM detections WHERE camera_id IN ({camera_ids});
    DELETE FROM cameras WHERE camera_id IN ({camera_ids});
    """
    subprocess.run(
        ["docker", "exec", "-i", "sentinel-postgres", "psql", "-U", "sentinel", "-d", "sentinel"],
        input=sql,
        text=True,
        check=True,
    )
    print("demo rows removed.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reset", action="store_true", help="remove the demo rows instead of seeding them"
    )
    args = parser.parse_args()

    try:
        if args.reset:
            reset()
        else:
            seed()
    except httpx.HTTPStatusError as exc:
        print(
            f"API call failed: {exc.request.url} -> {exc.response.status_code} {exc.response.text}",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc
    except httpx.ConnectError as exc:
        print(f"could not reach {API_BASE} — is core_api running?", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
