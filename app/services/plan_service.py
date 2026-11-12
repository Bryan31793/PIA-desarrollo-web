from app.core.exceptions import PlanNotFoundError
from app.infrastructure.plans.repository import plan_repository
from app.schemas.plans import PlanCreation, PlanPatch, PlanResponse


def create_plan(data: PlanCreation) -> PlanResponse:
    plan = plan_repository.create(data.name, data.price, data.duration_days)
    return PlanResponse.model_validate(plan)


def patch_plan(plan_id: int, data: PlanPatch) -> PlanResponse:
    plan = plan_repository.patch(plan_id, data.model_dump(exclude_unset=True))
    if plan is None:
        raise PlanNotFoundError()
    return PlanResponse.model_validate(plan)
