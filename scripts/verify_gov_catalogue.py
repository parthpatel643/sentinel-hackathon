#!/usr/bin/env python3
"""Verify the government catalogue client against the REAL endpoint.

The exact JSON shape of `cameras.json` was not confirmed at build time (see
edge_agent/adapters/gov_catalogue.py). Run this once real credentials are in
your local `.env` (copy `.env.example`) to check the tolerant parser actually
maps every field correctly, and to see the raw response if it doesn't.

Usage:
    uv run python scripts/verify_gov_catalogue.py
    uv run python scripts/verify_gov_catalogue.py --raw   # dump the raw JSON too
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "packages" / "sentinel_core" / "src"))
sys.path.insert(0, str(REPO_ROOT / "services" / "edge_agent" / "src"))


async def main(*, show_raw: bool) -> None:
    import httpx

    from edge_agent.adapters.gov_catalogue import GovCatalogueClient
    from sentinel_core.config import get_settings

    settings = get_settings()
    if not settings.gov_access_email or not settings.gov_access_password.get_secret_value():
        print(
            "SENTINEL_GOV_ACCESS_EMAIL / SENTINEL_GOV_ACCESS_PASSWORD are not set.\n"
            "Copy .env.example to .env and fill them in first.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    print(f"fetching {settings.gov_catalogue_url} ...")

    if show_raw:
        async with httpx.AsyncClient(timeout=10.0) as raw_client:
            response = await raw_client.get(settings.gov_catalogue_url)
            response.raise_for_status()
            print("--- raw response -------------------------------------------------")
            print(json.dumps(response.json(), indent=2)[:4000])
            print("--------------------------------------------------------------------")

    async with GovCatalogueClient(settings) as client:
        cameras = await client.fetch()

    print(f"\nparsed {len(cameras)} cameras\n")
    for cam in cameras[:10]:
        profile_protocols = [p.protocol.value for p in cam.profiles]
        print(
            f"  {cam.camera_id:10s} {cam.name:30s} dept={cam.department or '-':20s} "
            f"status={cam.status.value:10s} profiles={profile_protocols}"
        )
    if len(cameras) > 10:
        print(f"  ... and {len(cameras) - 10} more")

    if not cameras:
        print(
            "\nNo cameras parsed. Re-run with --raw to inspect the response shape, "
            "then adjust the key-alias tuples at the top of gov_catalogue.py.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    print(
        "\nSpot-check one entry's stream URLs "
        "(only the host:port/path pattern matters here, not the exact bytes):"
    )
    sample = cameras[0]
    for profile in sample.profiles:
        masked = profile.url.split("@")[-1] if "@" in profile.url else profile.url
        print(f"  {profile.protocol.value:6s} -> ...@{masked}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", action="store_true", help="also print the raw JSON response")
    args = parser.parse_args()
    asyncio.run(main(show_raw=args.raw))
