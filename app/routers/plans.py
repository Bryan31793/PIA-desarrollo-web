from typing import Annotated

from fastapi import APIRouter, Depends, Path, status

from app.core.roles import Role
from app.schemas.plans import PlanCreation, PlanPatch, PlanResponse
from app.services.auth_service import require_roles
from app.services.plan_service import create_plan, patch_plan

router = APIRouter(
    prefix="/api/plans",
    tags=["Plans"],
    dependencies=[Depends(require_roles(Role.ADMIN))],
)


@router.post(
    "",
    response_model=PlanResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        409: {"description": "Plan name already registered"},
        503: {"description": "Storage unavailable"},
    },
)
def create(data: PlanCreation) -> PlanResponse:
    return create_plan(data)


@router.patch(
    "/{plan_id}",
    response_model=PlanResponse,
    responses={
        404: {"description": "Plan not found"},
        409: {"description": "Plan name already registered"},
        503: {"description": "Storage unavailable"},
    },
)
def patch(
    plan_id: Annotated[int, Path(ge=-(2**63), le=2**63 - 1)], data: PlanPatch
) -> PlanResponse:
    return patch_plan(plan_id, data)
