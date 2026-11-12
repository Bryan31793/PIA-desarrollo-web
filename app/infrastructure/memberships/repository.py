from contextlib import nullcontext
from datetime import date
from typing import Any

from psycopg import Connection
from psycopg.errors import CheckViolation, ExclusionViolation, ForeignKeyViolation

from app.core.exceptions import (
    InvalidMembershipDatesError,
    MemberNotFoundError,
    MembershipOverlapError,
    PlanNotFoundError,
)
from app.infrastructure.database.db import get_connection


class MembershipRepository:
    def find_current_by_member_id(
        self, member_id: int, on_date: date
    ) -> dict[str, Any] | None:
        with get_connection() as connection:
            return connection.execute(
                """
                SELECT m.member_id, ms.membership_id, ms.plan_id,
                       p.name AS plan_name, ms.start_date, ms.end_date
                FROM members AS m
                LEFT JOIN memberships AS ms
                    ON ms.member_id = m.member_id
                    AND %s BETWEEN ms.start_date AND ms.end_date
                LEFT JOIN plans AS p ON p.plan_id = ms.plan_id
                WHERE m.member_id = %s
                """,
                (on_date, member_id),
            ).fetchone()

    def create(
        self,
        member_id: int,
        plan_id: int,
        start_date: date,
        end_date: date,
        *,
        connection: Connection[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        try:
            context = (
                nullcontext(connection) if connection is not None else get_connection()
            )
            with context as active_connection:
                # Serializa altas del mismo miembro antes de evaluar no_overlap.
                # NO KEY UPDATE permite las comprobaciones FK con KEY SHARE.
                active_connection.execute(
                    "SELECT member_id FROM members WHERE member_id = %s FOR NO KEY UPDATE",
                    (member_id,),
                )
                row = active_connection.execute(
                    """
                    INSERT INTO memberships (member_id, plan_id, start_date, end_date)
                    VALUES (%s, %s, %s, %s)
                    RETURNING membership_id, member_id, plan_id, start_date, end_date
                    """,
                    (member_id, plan_id, start_date, end_date),
                ).fetchone()
                if row is None:
                    raise RuntimeError("Membership insert returned no row")
                return row
        except ForeignKeyViolation as exc:
            if exc.diag.constraint_name == "memberships_member_id_fkey":
                raise MemberNotFoundError() from exc
            if exc.diag.constraint_name == "memberships_plan_id_fkey":
                raise PlanNotFoundError() from exc
            raise
        except ExclusionViolation as exc:
            if exc.diag.constraint_name == "no_overlap":
                raise MembershipOverlapError() from exc
            raise
        except CheckViolation as exc:
            if exc.diag.constraint_name == "memberships_check":
                raise InvalidMembershipDatesError() from exc
            raise


membership_repository = MembershipRepository()
