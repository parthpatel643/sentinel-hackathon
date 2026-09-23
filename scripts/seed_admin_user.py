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


async def seed(
    email: str, password: str, full_name: str, role: str, *, reset_password: bool = False
) -> None:
    session_factory = get_sessionmaker()
    async with session_factory() as session:
        existing = (
            await session.execute(select(User).where(User.email == email))
        ).scalar_one_or_none()
        if existing is not None:
            if not reset_password:
                print(f"{email} already exists (role={existing.role}) — nothing to do.")
                return
            # Rotating a password matters the moment this deployment stops
            # being localhost-only: the default in the README is documentation,
            # not a credential, and must not survive being exposed.
            existing.hashed_password = hash_password(password)
            await session.commit()
            print(f"reset password for {email}")
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
    parser.add_argument(
        "--reset-password",
        action="store_true",
        help="rotate the password if the account already exists (use before exposing this "
        "deployment beyond localhost).",
    )
    args = parser.parse_args()

    asyncio.run(
        seed(args.email, args.password, args.name, args.role, reset_password=args.reset_password)
    )


if __name__ == "__main__":
    main()
