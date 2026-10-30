from __future__ import annotations

import ipaddress
import hashlib
import logging
import secrets
import time
from collections import deque
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Any

import jwt
from fastapi import HTTPException, Request, status

from app.core.config import settings

logger = logging.getLogger('neuroage.security')

_RATE_LIMIT_BUCKETS: dict[tuple[str, str], deque[float]] = {}
_RATE_LIMIT_LOCK = Lock()
_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_KEY_LENGTH = 32
_SCRYPT_SALT_LENGTH = 16
_SCRYPT_MAX_MEMORY = 64 * 1024 * 1024


def redact_sensitive_value(value: str | None) -> str:
    if not value:
        return '<empty>'
    if len(value) <= 8:
        return '***'
    return f'{value[:2]}***{value[-2:]}'


def log_security_event(
    *,
    action: str,
    user_id: str | None,
    assessment_id: str | None = None,
    allowed: bool,
    reason: str | None = None,
) -> None:
    logger.warning(
        'security_event action=%s user=%s assessment=%s allowed=%s reason=%s',
        action,
        redact_sensitive_value(user_id),
        assessment_id,
        allowed,
        reason or 'ok',
    )


def get_client_address(request: Request) -> str:
    if request.client is not None:
        peer = request.client.host
        try:
            peer_ip = ipaddress.ip_address(peer)
        except ValueError:
            return peer

        trusted_networks = [
            ipaddress.ip_network(value, strict=False)
            for value in settings.trusted_proxy_ips
        ]
        if any(peer_ip in network for network in trusted_networks):
            forwarded = request.headers.get('X-Forwarded-For', '')
            chain = [value.strip() for value in forwarded.split(',') if value.strip()]
            for candidate in reversed(chain):
                try:
                    candidate_ip = ipaddress.ip_address(candidate)
                except ValueError:
                    continue
                if not any(candidate_ip in network for network in trusted_networks):
                    return str(candidate_ip)
        return str(peer_ip)
    return 'unknown-client'


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(_SCRYPT_SALT_LENGTH)
    derived_key = hashlib.scrypt(
        password.encode('utf-8'),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_SCRYPT_KEY_LENGTH,
        maxmem=_SCRYPT_MAX_MEMORY,
    )
    return (
        f'scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}'
        f'${salt.hex()}${derived_key.hex()}'
    )


def verify_password(password: str, password_hash: str) -> bool:
    try:
        scheme, n_value, r_value, p_value, salt_hex, key_hex = password_hash.split('$')
        if scheme != 'scrypt':
            return False
        n, r, p = int(n_value), int(r_value), int(p_value)
        salt = bytes.fromhex(salt_hex)
        expected_key = bytes.fromhex(key_hex)
        if n < 2 or n & (n - 1) or r < 1 or p < 1 or not salt or not expected_key:
            return False
        actual_key = hashlib.scrypt(
            password.encode('utf-8'),
            salt=salt,
            n=n,
            r=r,
            p=p,
            dklen=len(expected_key),
            maxmem=_SCRYPT_MAX_MEMORY,
        )
    except (ValueError, TypeError, OverflowError):
        return False
    return secrets.compare_digest(actual_key, expected_key)


def create_access_token(user_id: str) -> tuple[str, datetime]:
    issued_at = datetime.now(timezone.utc)
    expires_at = issued_at + timedelta(minutes=settings.access_token_expire_minutes)
    token = jwt.encode(
        {
            'sub': user_id,
            'iss': settings.jwt_issuer,
            'aud': settings.jwt_audience,
            'iat': issued_at,
            'exp': expires_at,
        },
        settings.secret_key,
        algorithm='HS256',
    )
    return token, expires_at


def _verify_access_token(token: str) -> str:
    try:
        claims = jwt.decode(
            token,
            settings.secret_key,
            algorithms=['HS256'],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
            options={'require': ['exp', 'iat', 'sub', 'aud', 'iss']},
        )
    except jwt.PyJWTError as exc:
        logger.info('Local access-token verification failed (%s).', type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='The access token is invalid or expired.',
        ) from exc

    user_id = claims.get('sub')
    if not isinstance(user_id, str) or not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='The access token does not identify an authenticated user.',
        )
    return user_id


def optional_user_context(request: Request) -> str | None:
    auth_header = request.headers.get('Authorization') or request.headers.get('authorization')
    if auth_header:
        scheme, _, token = auth_header.partition(' ')
        if scheme.lower() != 'bearer' or not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail='A valid bearer access token is required.',
            )
        if token.startswith('neuroage-assessment:'):
            return None
        return _verify_access_token(token)

    if request.headers.get('X-User-Id') or request.headers.get('x-user-id'):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='X-User-Id is not accepted. Sign in through the configured authentication provider.',
        )
    return None


def require_user_context(request: Request) -> str:
    user_id = optional_user_context(request)
    if user_id:
        return user_id
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail='Authentication required. Supply X-User-Id or Authorization: Bearer neuroage-user:<user_id>.',
    )


def get_assessment_token(request: Request) -> str | None:
    token = request.headers.get('X-Assessment-Token') or request.headers.get('x-assessment-token')
    if token and token.strip():
        return token.strip()

    auth_header = request.headers.get('Authorization') or request.headers.get('authorization')
    if auth_header:
        scheme, _, token_value = auth_header.partition(' ')
        if scheme.lower() == 'bearer' and token_value:
            if token_value.startswith('neuroage-assessment:'):
                token = token_value.split(':', 1)[1].strip()
                if token:
                    return token
    return None


def ensure_owned_assessment(assessment: dict[str, Any], user_id: str | None, *, action: str, access_token: str | None = None) -> None:
    owner_id = assessment.get('owner_id')
    access_match = bool(access_token) and assessment.get('access_token') == access_token

    if not user_id and not access_match:
        log_security_event(action=action, user_id=user_id, assessment_id=str(assessment.get('assessment_id')), allowed=False, reason='missing_assessment_access')
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Authentication required. Provide a user context or a valid assessment token.',
        )

    if owner_id in (None, 'anonymous'):
        if access_match:
            return
        if user_id and user_id == owner_id:
            return
        log_security_event(action=action, user_id=user_id, assessment_id=str(assessment.get('assessment_id')), allowed=False, reason='missing_assessment_access')
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='You are not authorized to access this assessment.',
        )
    if owner_id == user_id or access_match:
        return
    log_security_event(action=action, user_id=user_id, assessment_id=str(assessment.get('assessment_id')), allowed=False, reason='owner_mismatch')
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail='You are not authorized to access this assessment.',
    )


def check_rate_limit(request: Request, *, endpoint: str, limit_per_minute: int = 30) -> None:
    client_id = get_client_address(request)
    now = time.monotonic()
    key = (endpoint, client_id)
    with _RATE_LIMIT_LOCK:
        for old_key, old_bucket in list(_RATE_LIMIT_BUCKETS.items()):
            while old_bucket and now - old_bucket[0] > 60:
                old_bucket.popleft()
            if not old_bucket:
                _RATE_LIMIT_BUCKETS.pop(old_key, None)

        bucket = _RATE_LIMIT_BUCKETS.setdefault(key, deque())
        if len(bucket) >= limit_per_minute:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail='Rate limit exceeded. Please try again shortly.',
            )
        bucket.append(now)
        if len(_RATE_LIMIT_BUCKETS) > 10_000:
            oldest_key = next(iter(_RATE_LIMIT_BUCKETS))
            if oldest_key != key:
                _RATE_LIMIT_BUCKETS.pop(oldest_key, None)
