from collections.abc import Callable
from secrets import token_urlsafe
from typing import Annotated, Any

import jwt
from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from pwdlib.exceptions import UnknownHashError

from app.core.exceptions import (
    AuthError,
    InvalidCredentialsError,
    InvalidTokenError,
    PermissionDeniedError,
    TokenExpiredError,
)
from app.core.identity import AuthenticatedIdentity, parse_subject
from app.core.passwords import password_hasher
from app.core.roles import Role
from app.infrastructure.auth.authentication import create_token, decode_token
from app.infrastructure.auth.repository import refresh_token_repository
from app.infrastructure.employees.repository import employee_repository
from app.infrastructure.members.repository import member_repository
from app.schemas.auth import TokenPairResponse

ACCESS_TOKEN_SECONDS = 600
REFRESH_TOKEN_SECONDS = 7 * 24 * 60 * 60
# Verificar un hash aun sin cuenta evita omitir el trabajo costoso de Argon2.
_DUMMY_PASSWORD_HASH = password_hasher.hash(token_urlsafe(32))
_EMPLOYEE_ROLES = {"Admin": Role.ADMIN, "Staff": Role.STAFF}

oauth2_scheme_access = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


def _verify_password(account: dict[str, Any] | None, password: str) -> bool:
    stored_hash = account["password_hash"] if account else _DUMMY_PASSWORD_HASH
    try:
        password_matches = password_hasher.verify(password, stored_hash)
    except UnknownHashError:
        return False
    return bool(account and account["is_active"] and password_matches)


def authenticate(username: str, password: str) -> TokenPairResponse:
    """El username del formulario OAuth2 corresponde al correo del cliente."""
    member = member_repository.find_credentials_by_email(username)
    if not _verify_password(member, password) or member is None:
        raise InvalidCredentialsError("Invalid username or password")
    return _login_response(
        AuthenticatedIdentity(f"member:{member['member_id']}", Role.MEMBER)
    )


def authenticate_employee(username: str, password: str) -> TokenPairResponse:
    employee = employee_repository.find_credentials_by_email(username)
    if not _verify_password(employee, password) or employee is None:
        raise InvalidCredentialsError("Invalid username or password")
    role = _EMPLOYEE_ROLES.get(employee["role"])
    if role is None:
        raise InvalidCredentialsError("Invalid username or password")
    return _login_response(
        AuthenticatedIdentity(f"employee:{employee['employee_id']}", role)
    )


def _login_response(identity: AuthenticatedIdentity) -> TokenPairResponse:
    access_token, refresh_token = issue_token_pair(identity)
    return TokenPairResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=ACCESS_TOKEN_SECONDS,
    )


def issue_token_pair(identity: AuthenticatedIdentity) -> tuple[str, str]:
    access_token, access_token_id, access_expires_at = create_token(
        identity.subject, "access", ACCESS_TOKEN_SECONDS, role=identity.role
    )
    refresh_token, refresh_token_id, refresh_expires_at = create_token(
        identity.subject, "refresh", REFRESH_TOKEN_SECONDS
    )
    refresh_token_repository.add_pair(
        access_token_id,
        access_expires_at,
        refresh_token_id,
        refresh_expires_at,
    )
    return access_token, refresh_token


def verify_access_token(
    token: Annotated[str | None, Depends(oauth2_scheme_access)],
) -> AuthenticatedIdentity:
    if not token:
        raise AuthError("Bearer access token required")
    try:
        claims = decode_token(token)
    except jwt.ExpiredSignatureError as exc:
        raise TokenExpiredError("Access token expired") from exc
    except jwt.InvalidTokenError as exc:
        raise InvalidTokenError("Invalid access token") from exc

    try:
        identity = AuthenticatedIdentity(claims["sub"], Role(claims["role"]))
    except (KeyError, ValueError, TypeError, AttributeError) as exc:
        raise InvalidTokenError("Invalid access token identity or role") from exc
    token_id = claims.get("jti")
    if (
        claims.get("token_type") != "access"
        or not isinstance(token_id, str)
        or not token_id
        or not refresh_token_repository.is_access_token_active(token_id)
    ):
        raise InvalidTokenError("Access token is invalid, expired, or has been revoked")
    return identity


def require_roles(
    *roles: Role,
) -> Callable[..., AuthenticatedIdentity]:
    if not roles:
        raise ValueError("At least one allowed role is required")

    def check_role(
        identity: Annotated[AuthenticatedIdentity, Depends(verify_access_token)],
    ) -> AuthenticatedIdentity:
        if identity.role not in roles:
            raise PermissionDeniedError()
        return identity

    return check_role


def rotate_refresh_token(
    token: Annotated[str | None, Depends(oauth2_scheme_access)],
) -> tuple[str, str]:
    if not token:
        raise AuthError("Bearer refresh token required")
    try:
        claims = decode_token(token)
    except jwt.ExpiredSignatureError as exc:
        raise TokenExpiredError("Refresh token expired") from exc
    except jwt.InvalidTokenError as exc:
        raise InvalidTokenError("Invalid refresh token") from exc

    token_id = claims.get("jti")
    if (
        claims.get("token_type") != "refresh"
        or not isinstance(claims.get("sub"), str)
        or not isinstance(token_id, str)
        or not token_id
    ):
        raise InvalidTokenError("Invalid refresh token")
    try:
        kind, account_id = parse_subject(claims["sub"])
    except ValueError as exc:
        raise InvalidTokenError("Invalid refresh token subject") from exc

    # Resolver la cuenta antes de consumir permite reintentar si PostgreSQL falla.
    if kind == "member":
        account = member_repository.find_identity_by_id(account_id)
        role = Role.MEMBER
    else:
        account = employee_repository.find_identity_by_id(account_id)
        role = _EMPLOYEE_ROLES.get(account["role"]) if account else None
    if not account or not account["is_active"] or role is None:
        raise InvalidTokenError("Refresh token account is unavailable")
    if not refresh_token_repository.consume_refresh(token_id):
        raise InvalidTokenError("Refresh token is invalid or has already been used")
    return issue_token_pair(AuthenticatedIdentity(claims["sub"], role))
