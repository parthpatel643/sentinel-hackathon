"""Auth API request/response models."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

__all__ = ["LoginRequest", "TokenResponse", "UserCreate", "UserOut", "UserUpdate"]


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    full_name: str
    role: str
    department_id: UUID | None = None
    active: bool
    created_at: datetime


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str
    role: str = Field(default="operator", description="operator | admin")
    department_id: UUID | None = Field(
        default=None,
        description="M12 ABAC scope — null sees every department (the natural default for "
        "an HQ/admin account); set restricts to that department's own cameras plus any "
        "camera with no department assigned yet.",
    )


class UserUpdate(BaseModel):
    role: str | None = Field(default=None, description="operator | admin")
    active: bool | None = None
    department_id: UUID | None = Field(default=None, description="M12 ABAC scope — see UserCreate")
