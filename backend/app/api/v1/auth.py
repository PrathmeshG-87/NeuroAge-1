from __future__ import annotations

import re
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import (
    check_rate_limit,
    create_access_token,
    hash_password,
    require_user_context,
    verify_password,
)
from app.db.models import User
from app.db.session import get_db

router = APIRouter(prefix='/api/v1/auth', tags=['authentication'])
_EMAIL_PATTERN = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    full_name: str = Field(min_length=1, max_length=255)
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=128)

    @field_validator('full_name')
    @classmethod
    def normalize_full_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError('Full name is required.')
        return normalized

    @field_validator('email')
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not _EMAIL_PATTERN.fullmatch(normalized):
            raise ValueError('Enter a valid email address.')
        return normalized


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=128)

    @field_validator('email')
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not _EMAIL_PATTERN.fullmatch(normalized):
            raise ValueError('Enter a valid email address.')
        return normalized


def _user_payload(user: User) -> dict[str, str | None]:
    return {
        'id': user.id,
        'email': user.email,
        'display_name': user.display_name,
    }


def _token_payload(user: User) -> dict[str, Any]:
    token, expires_at = create_access_token(user.id)
    return {
        'access_token': token,
        'token_type': 'bearer',
        'expires_in': settings.access_token_expire_minutes * 60,
        'expires_at': expires_at.isoformat(),
        'user': _user_payload(user),
    }


@router.post('/register', status_code=status.HTTP_201_CREATED)
def register(
    payload: RegisterRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    check_rate_limit(
        request,
        endpoint='auth_register',
        limit_per_minute=min(settings.rate_limit_per_minute, 5),
    )
    existing_user = db.scalar(select(User).where(User.email == payload.email))
    if existing_user is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail='An account with this email address already exists.',
        )

    user = User(
        id=str(uuid.uuid4()),
        email=payload.email,
        display_name=payload.full_name,
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail='An account with this email address already exists.',
        ) from exc

    return {
        'message': 'Account created. You can now sign in.',
        'user': _user_payload(user),
    }


@router.post('/login')
def login(
    payload: LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    check_rate_limit(
        request,
        endpoint='auth_login',
        limit_per_minute=min(settings.rate_limit_per_minute, 10),
    )
    user = db.scalar(select(User).where(User.email == payload.email))
    if user is None or not verify_password(
        payload.password,
        user.password_hash if user is not None else '',
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Email or password is incorrect.',
            headers={'WWW-Authenticate': 'Bearer'},
        )
    return _token_payload(user)


@router.get('/me')
def get_current_user(
    user_id: str = Depends(require_user_context),
    db: Session = Depends(get_db),
) -> dict[str, dict[str, str | None]]:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='The account for this session no longer exists.',
            headers={'WWW-Authenticate': 'Bearer'},
        )
    return {'user': _user_payload(user)}
