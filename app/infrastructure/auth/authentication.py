from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import jwt

from app.core.auth_config import JWT_ALGORITHM, JWT_AUDIENCE, JWT_ISSUER, JWT_SECRET
from app.core.roles import Role


def create_token(
    subject: str, token_type: str, lifetime_seconds: int, *, role: Role | None = None
) -> tuple[str, str, datetime]:
    """
    Create a token

    Token claims:
    - sub
    - jti
    - iat
    - exp
    - iss
    - aud
    - token_type
    - role (access tokens only)

    Return:
    (token, token_id, expires_at)
    """
    token_id = str(uuid4())
    now = datetime.now(UTC)
    expires_at = now + timedelta(seconds=lifetime_seconds)
    claims: dict[str, Any] = {
        "sub": subject,
        "jti": token_id,
        "iat": now,
        "exp": expires_at,
        "iss": JWT_ISSUER,
        "aud": JWT_AUDIENCE,
        "token_type": token_type,
    }
    if token_type == "access":
        if not isinstance(role, Role):
            raise ValueError("An access token requires a role")
        claims["role"] = role.value
    elif token_type != "refresh":
        raise ValueError("Unknown token type")
    token = jwt.encode(claims, JWT_SECRET, JWT_ALGORITHM)
    return token, token_id, expires_at


def decode_token(token: str) -> dict[str, Any]:
    """
    Decode a token

    Token claims:
    - sub
    - jti
    - iat
    - exp
    - iss
    - aud
    - token_type

    Return:
    claims
    """
    claims = jwt.decode(
        token,
        JWT_SECRET,
        algorithms=[JWT_ALGORITHM],
        audience=JWT_AUDIENCE,
        issuer=JWT_ISSUER,
        options={
            "require": [
                "sub",
                "jti",
                "iat",
                "exp",
                "iss",
                "aud",
                "token_type",
            ]
        },
    )

    return claims
