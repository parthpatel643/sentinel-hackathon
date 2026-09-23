"""Auth HTTP API: login, "who am I", and (admin-only) user management."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from core_api.audit.service import record_audit_event
from core_api.auth.dependencies import current_user, require_role
from core_api.auth.schemas import LoginRequest, TokenResponse, UserCreate, UserOut, UserUpdate
from core_api.auth.service import (
    TokenPayload,
    authenticate_user,
    create_access_token,
    create_user,
    get_user_by_email,
    list_users,
    update_user,
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


@router.get("/users", response_model=list[UserOut])
async def list_users_endpoint(
    session: AsyncSession = Depends(get_session),
    _admin: TokenPayload = Depends(require_role("admin")),
) -> list[UserOut]:
    """Admin Portal's Users & roles screen (docs/03-UX-DESIGN.md §6)."""
    return [UserOut.model_validate(u) for u in await list_users(session)]


@router.post("/users", response_model=UserOut, status_code=201)
async def create_user_endpoint(
    payload: UserCreate,
    session: AsyncSession = Depends(get_session),
    admin: TokenPayload = Depends(require_role("admin")),
) -> UserOut:
    try:
        user = await create_user(
            session,
            email=payload.email,
            password=payload.password,
            full_name=payload.full_name,
            role=payload.role,
            department_id=payload.department_id,
        )
        await record_audit_event(
            session,
            actor_email=admin.email,
            action="user_created",
            resource_type="user",
            resource_id=str(user.id),
            detail={"email": user.email, "role": user.role},
        )
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=409, detail=f"a user with email {payload.email!r} already exists"
        ) from exc
    return UserOut.model_validate(user)


@router.patch("/users/{user_id}", response_model=UserOut)
async def update_user_endpoint(
    user_id: UUID,
    payload: UserUpdate,
    session: AsyncSession = Depends(get_session),
    admin: TokenPayload = Depends(require_role("admin")),
) -> UserOut:
    user = await update_user(
        session,
        user_id,
        role=payload.role,
        active=payload.active,
        department_id=payload.department_id,
    )
    if user is None:
        raise HTTPException(status_code=404, detail=f"no user with id {user_id}")
    await record_audit_event(
        session,
        actor_email=admin.email,
        action="user_updated",
        resource_type="user",
        resource_id=str(user_id),
        detail={"role": payload.role, "active": payload.active},
    )
    await session.commit()
    return UserOut.model_validate(user)
