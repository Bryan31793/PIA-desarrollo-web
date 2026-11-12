from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.core.identity import AuthenticatedIdentity
from app.core.roles import Role
from app.schemas.memberships import (
    MembershipRegistration,
    MembershipResponse,
    MembershipStatusResponse,
)
from app.services.auth_service import require_roles
from app.services.membership_service import (
    get_member_membership_status,
    register_membership,
)

router = APIRouter(prefix="/api/memberships", tags=["Memberships"])


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=MembershipResponse,
    description="Registra una membresía desde hoy y su pago en efectivo por el precio exacto del plan, en una sola transacción.",
    responses={
        401: {"description": "Invalid or missing access token"},
        403: {"description": "STAFF role required"},
        404: {"description": "Member or plan not found"},
        409: {"description": "Membership dates overlap"},
        422: {"description": "Invalid membership data or unsupported dates"},
        503: {"description": "Storage unavailable"},
    },
)
def register(
    data: MembershipRegistration,
    identity: Annotated[AuthenticatedIdentity, Depends(require_roles(Role.STAFF))],
) -> MembershipResponse:
    return register_membership(data, identity)


@router.get(
    "/me",
    response_model=MembershipStatusResponse,
    description="Consulta el plan vigente del miembro autenticado, incluyendo las fechas inicial y final.",
    responses={
        401: {"description": "Invalid or missing access token"},
        403: {"description": "MEMBER role required"},
        404: {"description": "Member not found"},
        503: {"description": "Storage unavailable"},
    },
)
def current_status(
    identity: Annotated[AuthenticatedIdentity, Depends(require_roles(Role.MEMBER))],
) -> MembershipStatusResponse:
    return get_member_membership_status(identity)
