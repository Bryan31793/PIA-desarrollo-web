from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordRequestForm

from app.core.identity import AuthenticatedIdentity
from app.core.roles import Role
from app.schemas.auth import ProtectedResponse, TokenPairResponse
from app.services.auth_service import (
    ACCESS_TOKEN_SECONDS,
    authenticate,
    authenticate_employee,
    require_roles,
    rotate_refresh_token,
    verify_access_token,
)

router = APIRouter()


@router.post(
    "/auth/login",
    response_model=TokenPairResponse,
    description="Inicia sesión con el correo del cliente en el campo username.",
)
def login(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
) -> TokenPairResponse:
    return authenticate(form_data.username, form_data.password)


@router.post(
    "/auth/employees/login",
    response_model=TokenPairResponse,
    description="Inicia sesión con el correo del empleado en el campo username.",
)
def employee_login(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
) -> TokenPairResponse:
    return authenticate_employee(form_data.username, form_data.password)


@router.post("/auth/refresh", response_model=TokenPairResponse)
def refresh(
    tokens: Annotated[tuple[str, str], Depends(rotate_refresh_token)],
) -> TokenPairResponse:
    access, refresh = tokens
    return TokenPairResponse(
        access_token=access,
        refresh_token=refresh,
        expires_in=ACCESS_TOKEN_SECONDS,
    )


@router.get("/api/protected", response_model=ProtectedResponse)
def protected_resource(
    identity: Annotated[AuthenticatedIdentity, Depends(verify_access_token)],
) -> ProtectedResponse:
    return ProtectedResponse(
        message="Access granted", subject=identity.subject, role=identity.role
    )


@router.get("/api/employees/protected", response_model=ProtectedResponse)
def employee_resource(
    identity: Annotated[
        AuthenticatedIdentity, Depends(require_roles(Role.ADMIN, Role.STAFF))
    ],
) -> ProtectedResponse:
    return ProtectedResponse(
        message="Access granted", subject=identity.subject, role=identity.role
    )
