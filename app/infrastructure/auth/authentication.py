import jwt
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from typing import Any

from app.core.auth_config import *




def create_token(
    username: str, token_type: str, lifetime_seconds: int
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

    Return:
    (token, token_id, expires_at)
    """
    token_id = str(uuid4())
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(seconds=lifetime_seconds)
    claims: dict[str, Any] = {
        "sub": username,
        "jti": token_id,
        "iat": now,
        "exp": expires_at,
        "iss": JWT_ISSUER,
        "aud": JWT_AUDIENCE,
        "token_type": token_type,
    }
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

