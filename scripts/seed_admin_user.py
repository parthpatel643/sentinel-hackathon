#!/usr/bin/env python3
"""Seeds a default operator account so there is a way to log in at all —
without this, the M6 auth gate would lock everyone out of a fresh
deployment with no bootstrap path. Idempotent: safe to re-run.

Usage:
    uv run python scripts/seed_admin_user.py
    uv run python scripts/seed_admin_user.py --email you@example.com \
        --password 'whatever' --name "Your Name"
"""

from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import select

from core_api.auth.service import hash_password
from core_api.db.base import get_sessionmaker
from core_api.db.models import User

DEFAULT_EMAIL = "admin@sentinel-platform.com"
DEFAULT_PASSWORD = "sentinel-admin-2026"
DEFAULT_NAME = "Sentinel Admin"


async def seed(email: str, password: str, full_name: str, role: str) -> None:
    session_factory = get_sessionmaker()
    async with session_factory() as session:
        existing = (
            await session.execute(select(User).where(User.email == email))
        ).scalar_one_or_none()
        if existing is not None:
            print(f"{email} already exists (role={existing.role}) — nothing to do.")
            return

        user = User(
            email=email, hashed_password=hash_password(password), full_name=full_name, role=role
        )
        session.add(user)
        await session.commit()
        print(f"created {role} account: {email} / {password}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", default=DEFAULT_EMAIL)
    parser.add_argument("--password", default=DEFAULT_PASSWORD)
    parser.add_argument("--name", default=DEFAULT_NAME)
    parser.add_argument("--role", default="admin", choices=["operator", "admin"])
    args = parser.parse_args()

    asyncio.run(seed(args.email, args.password, args.name, args.role))


if __name__ == "__main__":
    main()
