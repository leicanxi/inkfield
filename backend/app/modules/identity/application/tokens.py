from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import jwt

from app.core.errors import AppError
from app.modules.identity.domain.entities import AccessClaims, LoginSession


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def hash_refresh_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


class AccessTokenCodec:
    def __init__(self, signing_key: str, issuer: str) -> None:
        self._signing_key = signing_key
        self._issuer = issuer

    def encode(self, login: LoginSession, issued_at: datetime, expires_at: datetime) -> str:
        payload = {
            "sub": str(login.user_id),
            "sid": str(login.session_id),
            "av": login.auth_version,
            "sv": login.session_version,
            "iat": issued_at,
            "exp": expires_at,
            "iss": self._issuer,
        }
        return jwt.encode(payload, self._signing_key, algorithm="HS256")

    def decode(self, raw_token: str) -> AccessClaims:
        try:
            payload: dict[str, Any] = jwt.decode(
                raw_token,
                self._signing_key,
                algorithms=["HS256"],
                issuer=self._issuer,
                options={
                    "require": ["sub", "sid", "av", "sv", "iat", "exp", "iss"],
                    "verify_exp": False,
                    "verify_iat": False,
                },
            )
            return AccessClaims(
                user_id=UUID(payload["sub"]),
                session_id=UUID(payload["sid"]),
                auth_version=int(payload["av"]),
                session_version=int(payload["sv"]),
                issued_at=datetime.fromtimestamp(int(payload["iat"]), tz=UTC),
                expires_at=datetime.fromtimestamp(int(payload["exp"]), tz=UTC),
            )
        except (jwt.PyJWTError, KeyError, TypeError, ValueError) as exc:
            raise AppError(
                "AUTH_ACCESS_TOKEN_INVALID",
                "The access token is invalid or expired.",
                status_code=401,
            ) from exc
