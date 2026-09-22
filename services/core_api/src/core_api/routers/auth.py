"""Auth HTTP API: login and "who am I"."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from core_api.auth.dependencies import current_user
from core_api.auth.schemas import LoginRequest, TokenResponse, UserOut
from core_api.auth.service import (
    TokenPayload,
    authenticate_user,
    create_access_token,
    get_user_by_email,
)
from core_api.db.base import get_session
from sentinel_core.config import get_settings

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login_endpoint(
    payload: LoginRequest, session: AsyncSession = Depends(get_session)
) -> TokenResponse:
    user = await authenticate_user(session, payload.email, payload.password)
    if user is None:
        # Deliberately the same message whether the email doesn't exist or
        # the password is wrong — distinguishing the two lets an attacker
        # enumerate valid accounts.
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    token = create_access_token(user, get_settings())
    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserOut)
async def me_endpoint(
    token: TokenPayload = Depends(current_user), session: AsyncSession = Depends(get_session)
) -> UserOut:
    user = await get_user_by_email(session, token.email)
    if user is None:
        raise HTTPException(status_code=404, detail="User no longer exists")
    return UserOut.model_validate(user)
