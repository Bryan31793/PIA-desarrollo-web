import hmac

import jwt

from app.core.exceptions import InvalidTokenError, TokenExpiredError
from app.infrastructure.auth.authentication import create_token, decode_token
from app.infrastructure.auth.repository import refresh_token_repository

DEMO_USERNAME = "demo"
DEMO_PASSWORD = "demo-password"
ACCESS_TOKEN_SECONDS = 600
REFRESH_TOKEN_SECONDS = 7 * 24 * 60 * 60

# TODO:
# - Tiene que consultar la base de datos  
def authenticate(username: str, password: str) -> bool:
    username_matches = hmac.compare_digest(
        username.encode("utf-8"), DEMO_USERNAME.encode("utf-8")
    )
    password_matches = hmac.compare_digest(
        password.encode("utf-8"), DEMO_PASSWORD.encode("utf-8")
    )
    return username_matches and password_matches


def issue_token_pair(username: str) -> tuple[str, str]:
    access_token, access_token_id, access_expires_at = create_token(
        username, "access", ACCESS_TOKEN_SECONDS
    )
    refresh_token, refresh_token_id, refresh_expires_at = create_token(
        username, "refresh", REFRESH_TOKEN_SECONDS
    )
    refresh_token_repository.add_pair(
        access_token_id,
        access_expires_at,
        refresh_token_id,
        refresh_expires_at,
    )
    return access_token, refresh_token


def verify_access_token(token: str) -> str:
    try:
        claims = decode_token(token)
    except jwt.ExpiredSignatureError as exc:
        raise TokenExpiredError("Access token expired") from exc
    except jwt.InvalidTokenError as exc:
        raise InvalidTokenError(
            "Invalid access token"
        ) from exc

    username = claims.get("sub")
    token_id = claims.get("jti")
    if (
        claims.get("token_type") != "access"
        or not isinstance(username, str)
        or not isinstance(token_id, str)
        or not refresh_token_repository.is_access_token_active(token_id)
    ):
        raise InvalidTokenError(
            "Access token is invalid, expired, or has been revoked",
        )
    return username


def rotate_refresh_token(token: str) -> tuple[str, str]:
    try:
        claims = decode_token(token)
    except jwt.ExpiredSignatureError as exc:
        raise TokenExpiredError("Refresh token expired") from exc
    except jwt.InvalidTokenError as exc:
        raise InvalidTokenError(
            "Invalid refresh token",
        ) from exc

    username = claims.get("sub")
    token_id = claims.get("jti")
    if (
        claims.get("token_type") != "refresh"
        or not isinstance(username, str)
        or not isinstance(token_id, str)
        or not refresh_token_repository.consume_refresh(token_id)
    ):
        raise InvalidTokenError(
            "Refresh token is invalid or has already been used",
        )
    return issue_token_pair(username)
