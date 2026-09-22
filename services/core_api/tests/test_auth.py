"""Auth: password hashing, JWT issuance/verification, and the authenticate
flow against a real Postgres. See conftest.py for the transaction-rollback
isolation — nothing here is ever actually persisted once a test ends."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
import pytest
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession

from core_api.auth.service import (
    InvalidTokenError,
    authenticate_user,
    create_access_token,
    decode_access_token,
    get_user_by_email,
    hash_password,
    verify_password,
)
from core_api.db.models import User
from sentinel_core.config import Settings


def _settings() -> Settings:
    return Settings(
        jwt_secret=SecretStr("test-secret-at-least-32-bytes-long"), jwt_algorithm="HS256"
    )


def test_hash_password_never_stores_the_plaintext() -> None:
    hashed = hash_password("correct horse battery staple")
    assert hashed != "correct horse battery staple"
    assert verify_password("correct horse battery staple", hashed)


def test_verify_password_rejects_a_wrong_password() -> None:
    hashed = hash_password("the-real-password")
    assert not verify_password("a-guess", hashed)


def test_verify_password_fails_closed_on_a_malformed_hash() -> None:
    """A hand-edited or corrupted hash must reject, not raise past the
    login endpoint as an unhandled 500."""
    assert not verify_password("anything", "not-a-real-bcrypt-hash")


async def test_create_and_decode_access_token_round_trips(db_session: AsyncSession) -> None:
    user = User(
        email="alice@example.com",
        hashed_password=hash_password("s3cret!"),
        full_name="Alice Operator",
        role="operator",
    )
    db_session.add(user)
    await db_session.flush()

    settings = _settings()
    token = create_access_token(user, settings)
    payload = decode_access_token(token, settings)

    assert payload.user_id == str(user.id)
    assert payload.email == "alice@example.com"
    assert payload.role == "operator"


def test_decode_access_token_rejects_garbage() -> None:
    with pytest.raises(InvalidTokenError):
        decode_access_token("not.a.real.token", _settings())


def test_decode_access_token_rejects_a_token_signed_with_a_different_secret() -> None:
    other_settings = Settings(
        jwt_secret=SecretStr("a-different-secret-also-32-bytes-plus"), jwt_algorithm="HS256"
    )
    forged = jwt.encode(
        {"sub": "x", "email": "x@example.com", "role": "operator"},
        other_settings.jwt_secret.get_secret_value(),
        algorithm="HS256",
    )
    with pytest.raises(InvalidTokenError):
        decode_access_token(forged, _settings())


def test_decode_access_token_rejects_an_expired_token() -> None:
    settings = _settings()
    now = datetime.now(UTC)
    expired = jwt.encode(
        {
            "sub": "x",
            "email": "x@example.com",
            "role": "operator",
            "iat": now - timedelta(hours=2),
            "exp": now - timedelta(hours=1),
        },
        settings.jwt_secret.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )
    with pytest.raises(InvalidTokenError):
        decode_access_token(expired, settings)


def test_decode_access_token_rejects_a_token_missing_claims() -> None:
    settings = _settings()
    incomplete = jwt.encode(
        {"sub": "x"}, settings.jwt_secret.get_secret_value(), algorithm=settings.jwt_algorithm
    )
    with pytest.raises(InvalidTokenError):
        decode_access_token(incomplete, settings)


async def test_authenticate_user_succeeds_with_the_right_password(db_session: AsyncSession) -> None:
    db_session.add(
        User(
            email="bob@example.com",
            hashed_password=hash_password("hunter2"),
            full_name="Bob Operator",
            role="operator",
        )
    )
    await db_session.flush()

    user = await authenticate_user(db_session, "bob@example.com", "hunter2")

    assert user is not None
    assert user.email == "bob@example.com"


async def test_authenticate_user_fails_with_the_wrong_password(db_session: AsyncSession) -> None:
    db_session.add(
        User(
            email="carol@example.com",
            hashed_password=hash_password("correct-password"),
            full_name="Carol Operator",
            role="operator",
        )
    )
    await db_session.flush()

    assert await authenticate_user(db_session, "carol@example.com", "wrong-password") is None


async def test_authenticate_user_fails_for_an_unknown_email(db_session: AsyncSession) -> None:
    assert await authenticate_user(db_session, "nobody@example.com", "irrelevant") is None


async def test_authenticate_user_fails_for_an_inactive_account(db_session: AsyncSession) -> None:
    db_session.add(
        User(
            email="dave@example.com",
            hashed_password=hash_password("s3cret!"),
            full_name="Dave Ex-Operator",
            role="operator",
            active=False,
        )
    )
    await db_session.flush()

    assert await authenticate_user(db_session, "dave@example.com", "s3cret!") is None


async def test_get_user_by_email_returns_none_for_an_unknown_address(
    db_session: AsyncSession,
) -> None:
    assert await get_user_by_email(db_session, "ghost@example.com") is None
