"""Auth API request/response models."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

__all__ = ["LoginRequest", "TokenResponse", "UserOut"]


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
    active: bool
    created_at: datetime
