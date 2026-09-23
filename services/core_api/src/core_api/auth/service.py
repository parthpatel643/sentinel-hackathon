"""Password hashing and JWT issuance/verification.

A real login gate for the Operator Console, not a placeholder: every
protected route (see routers/*.py's `dependencies=[Depends(...)]`) fails
closed without a valid, unexpired token. Full OIDC/RBAC/ABAC and Postgres
row-level-security tenancy is M12's scope (docs/05-DELIVERY-PLAN.md) — this
is deliberately the minimum that makes "anyone can hit every endpoint" false,
not a finished security model.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core_api.db.models import User
from sentinel_core.config import Settings

__all__ = [
    "InvalidTokenError",
    "TokenPayload",
    "authenticate_user",
    "create_access_token",
    "create_user",
    "decode_access_token",
    "get_user_by_email",
    "hash_password",
    "list_users",
    "update_user",
    "verify_password",
]


class InvalidTokenError(ValueError):
    """Raised for any token that fails to decode/verify — expired, forged,
    wrong signature, or missing the claims this app requires. One exception
    type so the FastAPI dependency that catches it doesn't need to know
    PyJWT's own exception hierarchy."""


@dataclass(frozen=True, slots=True)
class TokenPayload:
    user_id: str
    email: str
    role: str
    department_id: str | None = None


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("ascii"))
    except ValueError:
        # A malformed hash (e.g. hand-edited in the DB) must fail closed,
        # not raise past the login endpoint as a 500.
        return False


def create_access_token(user: User, settings: Settings) -> str:
    now = datetime.now(UTC)
    claims: dict[str, Any] = {
        "sub": str(user.id),
        "email": user.email,
        "role": user.role,
        "department_id": str(user.department_id) if user.department_id else None,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expires_minutes),
    }
    return jwt.encode(
        claims, settings.jwt_secret.get_secret_value(), algorithm=settings.jwt_algorithm
    )


def decode_access_token(token: str, settings: Settings) -> TokenPayload:
    try:
        claims = jwt.decode(
            token, settings.jwt_secret.get_secret_value(), algorithms=[settings.jwt_algorithm]
        )
    except jwt.PyJWTError as exc:
        raise InvalidTokenError(str(exc)) from exc

    user_id = claims.get("sub")
    email = claims.get("email")
    role = claims.get("role")
    if not user_id or not email or not role:
        raise InvalidTokenError("token is missing required claims")
    return TokenPayload(
        user_id=user_id, email=email, role=role, department_id=claims.get("department_id")
    )


async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    result = await session.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def authenticate_user(session: AsyncSession, email: str, password: str) -> User | None:
    user = await get_user_by_email(session, email)
    if user is None or not user.active:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user


async def list_users(session: AsyncSession) -> list[User]:
    result = await session.execute(select(User).order_by(User.email))
    return list(result.scalars().all())


async def create_user(
    session: AsyncSession,
    *,
    email: str,
    password: str,
    full_name: str,
    role: str,
    department_id: uuid.UUID | None = None,
) -> User:
    user = User(
        email=email,
        hashed_password=hash_password(password),
        full_name=full_name,
        role=role,
        department_id=department_id,
    )
    session.add(user)
    await session.flush()
    return user


async def update_user(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    role: str | None,
    active: bool | None,
    department_id: uuid.UUID | None = None,
) -> User | None:
    user = await session.get(User, user_id)
    if user is None:
        return None
    if role is not None:
        user.role = role
    if active is not None:
        user.active = active
    if department_id is not None:
        user.department_id = department_id
    await session.flush()
    return user
