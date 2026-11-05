from fastapi import APIRouter, Depends, Request
from fastapi.security import HTTPBearer

from app.core.exceptions import InvalidCredentialsError
from app.schemas.auth import (
    LoginRequest,
    ProtectedResponse,
    RefreshRequest,
    TokenPairResponse,
)
from app.services.auth_service import (
    ACCESS_TOKEN_SECONDS,
    authenticate,
    issue_token_pair,
    rotate_refresh_token,
)

router = APIRouter()
bearer_scheme = HTTPBearer(
    bearerFormat="JWT",
    description="Pega el access_token obtenido en /auth/login, sin el prefijo Bearer.",
    auto_error=False,
)


@router.post("/auth/login", response_model=TokenPairResponse)
def login(credentials: LoginRequest) -> TokenPairResponse:
    if not authenticate(credentials.username, credentials.password):
        raise InvalidCredentialsError("Invalid username or password")
    access_token, refresh_token = issue_token_pair(credentials.username)
    return TokenPairResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=ACCESS_TOKEN_SECONDS,
    )


@router.post("/auth/refresh", response_model=TokenPairResponse)
def refresh(request: RefreshRequest) -> TokenPairResponse:
    access_token, refresh_token = rotate_refresh_token(request.refresh_token)
    return TokenPairResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=ACCESS_TOKEN_SECONDS,
    )


@router.get(
    "/api/protected",
    response_model=ProtectedResponse,
    dependencies=[Depends(bearer_scheme)],
)
def protected_resource(request: Request) -> ProtectedResponse:
    return ProtectedResponse(
        message="Access granted",
        username=request.state.username,
    )
