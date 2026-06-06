"""Authentication endpoints."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app import db
from app.services.auth import (
    EmailAlreadyRegistered,
    SignupInput,
    WeakPassword,
    signup_user,
    user_public_payload,
)


router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

DbSession = Annotated[Session, Depends(db.get_db_session)]


class SignupRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=8, max_length=128)
    nickname: str | None = Field(default=None, max_length=40)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if "@" not in normalized or normalized.startswith("@") or normalized.endswith("@"):
            raise ValueError("invalid_email")
        return normalized


@router.post("/signup", status_code=status.HTTP_201_CREATED)
def signup(payload: SignupRequest, session: DbSession):
    try:
        user = signup_user(
            session,
            SignupInput(
                email=payload.email,
                password=payload.password,
                nickname=payload.nickname,
            ),
        )
    except EmailAlreadyRegistered as exc:
        raise HTTPException(status_code=409, detail=exc.code) from exc
    except WeakPassword as exc:
        raise HTTPException(status_code=422, detail=exc.code) from exc

    return {"user": user_public_payload(user)}
