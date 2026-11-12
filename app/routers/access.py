from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.core.identity import AuthenticatedIdentity
from app.core.roles import Role
from app.schemas.access import AccessPassResponse, CheckInRequest, CheckInResponse
from app.services.access_service import generate_access_pass, register_check_in
from app.services.auth_service import require_roles

router = APIRouter(tags=["Gym access"])


@router.post(
    "/api/access-passes",
    response_model=AccessPassResponse,
    status_code=status.HTTP_201_CREATED,
    description="Genera el contenido de un QR de un uso válido por 120 segundos e invalida los anteriores.",
    responses={
        401: {"description": "Invalid access token"},
        403: {"description": "MEMBER, active account and membership required"},
        404: {"description": "Member not found"},
        409: {"description": "Member has already checked in today"},
        503: {"description": "Storage unavailable"},
    },
)
def create_access_pass(
    response: Response,
    identity: Annotated[AuthenticatedIdentity, Depends(require_roles(Role.MEMBER))],
) -> AccessPassResponse:
    response.headers["Cache-Control"] = "no-store"
    return generate_access_pass(identity)


@router.post(
    "/api/check-ins",
    response_model=CheckInResponse,
    status_code=status.HTTP_201_CREATED,
    description="Escanea un pase válido y registra inmediatamente la entrada; solo STAFF.",
    responses={
        401: {"description": "Invalid access token or missing employee"},
        403: {"description": "STAFF, active member account and membership required"},
        404: {"description": "Member not found"},
        409: {
            "description": "Invalid, expired, invalidated or consumed pass, or daily entry already registered"
        },
        503: {"description": "Storage unavailable"},
    },
)
def check_in(
    data: CheckInRequest,
    identity: Annotated[AuthenticatedIdentity, Depends(require_roles(Role.STAFF))],
) -> CheckInResponse:
    return register_check_in(data, identity)
