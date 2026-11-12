from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.core.exceptions import (
    InvalidPlanPriceError,
    MemberNotFoundError,
    MembershipDateOutOfRangeError,
    PlanNotFoundError,
)
from app.core.identity import AuthenticatedIdentity, parse_subject
from app.infrastructure.database.db import get_connection
from app.infrastructure.memberships.repository import membership_repository
from app.infrastructure.payments.repository import payment_repository
from app.infrastructure.plans.repository import plan_repository
from app.schemas.memberships import (
    CurrentMembershipResponse,
    MembershipRegistration,
    MembershipResponse,
    MembershipStatusResponse,
)


def get_membership_start_date() -> date:
    """Fecha local del gimnasio, independiente de la zona horaria del servidor."""
    return datetime.now(ZoneInfo("America/Monterrey")).date()


def register_membership(
    data: MembershipRegistration, identity: AuthenticatedIdentity
) -> MembershipResponse:
    _, employee_id = parse_subject(identity.subject)
    with get_connection() as connection:
        # FOR SHARE conserva precio y duración hasta confirmar el alta y el pago.
        plan = plan_repository.find_by_id(data.plan_id, connection=connection)
        if plan is None:
            raise PlanNotFoundError()
        amount = plan["price"]
        if not amount.is_finite() or amount <= 0:
            raise InvalidPlanPriceError()
        start_date = get_membership_start_date()
        try:
            end_date = start_date + timedelta(days=plan["duration_days"])
        except OverflowError as exc:
            raise MembershipDateOutOfRangeError() from exc
        membership = membership_repository.create(
            data.member_id, data.plan_id, start_date, end_date, connection=connection
        )
        payment = payment_repository.create(
            membership["membership_id"], employee_id, amount, connection=connection
        )
        response = MembershipResponse.model_validate({**membership, "payment": payment})
    return response


def get_member_membership_status(
    identity: AuthenticatedIdentity,
) -> MembershipStatusResponse:
    _, member_id = parse_subject(identity.subject)
    current = membership_repository.find_current_by_member_id(
        member_id, get_membership_start_date()
    )
    if current is None:
        raise MemberNotFoundError()
    if current["membership_id"] is None:
        return MembershipStatusResponse(has_active_plan=False, membership=None)
    return MembershipStatusResponse(
        has_active_plan=True,
        membership=CurrentMembershipResponse.model_validate(current),
    )
