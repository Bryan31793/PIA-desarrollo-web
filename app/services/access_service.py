from datetime import UTC, datetime, time, timedelta
from hashlib import sha256
from secrets import token_urlsafe
from typing import Any
from zoneinfo import ZoneInfo

from psycopg import Connection

from app.core.exceptions import (
    AccessPassUnavailableError,
    ActiveMembershipRequiredError,
    DailyCheckInLimitError,
    InactiveMemberError,
    MemberNotFoundError,
)
from app.core.identity import AuthenticatedIdentity, parse_subject
from app.infrastructure.access.repository import access_repository
from app.infrastructure.database.db import get_connection
from app.schemas.access import AccessPassResponse, CheckInRequest, CheckInResponse

ACCESS_PASS_SECONDS = 120
_GYM_TIMEZONE = ZoneInfo("America/Monterrey")


def get_access_time() -> datetime:
    return datetime.now(UTC)


def _lock_eligible_member(
    member_id: int, connection: Connection[dict[str, Any]]
) -> dict[str, Any]:
    # Generación y escaneo toman primero el mismo bloqueo de miembro.
    member = access_repository.lock_member(member_id, connection=connection)
    if member is None:
        raise MemberNotFoundError()
    if not member["is_active"]:
        raise InactiveMemberError()
    return member


def _lock_current_membership(
    member_id: int, connection: Connection[dict[str, Any]]
) -> dict[str, Any]:
    today = get_access_time().astimezone(_GYM_TIMEZONE).date()
    membership = access_repository.find_active_membership(
        member_id, today, connection=connection
    )
    # Reevalúa la fecha después de adquirir el bloqueo por un posible cambio de día.
    today = get_access_time().astimezone(_GYM_TIMEZONE).date()
    if (
        membership is None
        or not membership["start_date"] <= today <= membership["end_date"]
    ):
        raise ActiveMembershipRequiredError()
    return membership


def _ensure_daily_entry_available(
    member_id: int, now: datetime, connection: Connection[dict[str, Any]]
) -> None:
    today = now.astimezone(_GYM_TIMEZONE).date()
    start = datetime.combine(today, time.min, tzinfo=_GYM_TIMEZONE)
    end = start + timedelta(days=1)
    # El bloqueo de miembro se mantiene desde antes de esta comprobación hasta COMMIT.
    if access_repository.has_check_in_between(
        member_id, start.astimezone(UTC), end.astimezone(UTC), connection=connection
    ):
        raise DailyCheckInLimitError()


def generate_access_pass(identity: AuthenticatedIdentity) -> AccessPassResponse:
    _, member_id = parse_subject(identity.subject)
    with get_connection() as connection:
        _lock_eligible_member(member_id, connection)
        _lock_current_membership(member_id, connection)
        now = get_access_time()
        _ensure_daily_entry_available(member_id, now, connection)
        pass_token = token_urlsafe(32)
        token_hash = sha256(pass_token.encode()).hexdigest()
        expires_at = now + timedelta(seconds=ACCESS_PASS_SECONDS)
        access_repository.invalidate_pending(member_id, now, connection=connection)
        access_repository.create_pass(
            member_id, token_hash, now, expires_at, connection=connection
        )
        response = AccessPassResponse(
            pass_token=pass_token, expires_at=expires_at, expires_in=ACCESS_PASS_SECONDS
        )
    return response


def register_check_in(
    data: CheckInRequest, identity: AuthenticatedIdentity
) -> CheckInResponse:
    _, employee_id = parse_subject(identity.subject)
    token_hash = sha256(data.pass_token.get_secret_value().encode()).hexdigest()
    with get_connection() as connection:
        reference = access_repository.find_pass_member(
            token_hash, connection=connection
        )
        if reference is None:
            raise AccessPassUnavailableError()
        member = _lock_eligible_member(reference["member_id"], connection)
        access_pass = access_repository.lock_pass(token_hash, connection=connection)
        if (
            access_pass is None
            or access_pass["member_id"] != member["member_id"]
            or access_pass["consumed_at"] is not None
            or access_pass["invalidated_at"] is not None
            or access_pass["expires_at"] <= get_access_time()
        ):
            raise AccessPassUnavailableError()
        membership = _lock_current_membership(member["member_id"], connection)
        now = get_access_time()
        if access_pass["expires_at"] <= now:
            raise AccessPassUnavailableError()
        _ensure_daily_entry_available(member["member_id"], now, connection)
        access_repository.consume_pass(
            access_pass["access_pass_id"], now, connection=connection
        )
        check_in = access_repository.create_check_in(
            access_pass["access_pass_id"],
            membership["membership_id"],
            employee_id,
            now,
            connection=connection,
        )
        response = CheckInResponse.model_validate(
            {
                **check_in,
                "member_id": member["member_id"],
                "member_name": member["name"],
            }
        )
    return response
