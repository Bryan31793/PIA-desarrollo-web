from datetime import date, datetime
from typing import Any

from psycopg import Connection
from psycopg.errors import ForeignKeyViolation

from app.core.exceptions import InvalidTokenError


class AccessRepository:
    def lock_member(
        self, member_id: int, *, connection: Connection[dict[str, Any]]
    ) -> dict[str, Any] | None:
        return connection.execute(
            """
            SELECT member_id, name, is_active FROM members
            WHERE member_id = %s FOR NO KEY UPDATE
            """,
            (member_id,),
        ).fetchone()

    def find_active_membership(
        self, member_id: int, on_date: date, *, connection: Connection[dict[str, Any]]
    ) -> dict[str, Any] | None:
        return connection.execute(
            """
            SELECT membership_id, start_date, end_date FROM memberships
            WHERE member_id = %s AND %s BETWEEN start_date AND end_date
            FOR SHARE
            """,
            (member_id, on_date),
        ).fetchone()

    def has_check_in_between(
        self,
        member_id: int,
        start: datetime,
        end: datetime,
        *,
        connection: Connection[dict[str, Any]],
    ) -> bool:
        row = connection.execute(
            """
            SELECT EXISTS (
                SELECT 1 FROM check_ins AS c
                JOIN access_passes AS p ON p.access_pass_id = c.access_pass_id
                WHERE p.member_id = %s
                    AND c.checked_in_at >= %s AND c.checked_in_at < %s
            ) AS checked_in
            """,
            (member_id, start, end),
        ).fetchone()
        return row["checked_in"]

    def invalidate_pending(
        self, member_id: int, now: datetime, *, connection: Connection[dict[str, Any]]
    ) -> None:
        connection.execute(
            """
            UPDATE access_passes SET invalidated_at = %s
            WHERE member_id = %s AND consumed_at IS NULL AND invalidated_at IS NULL
            """,
            (now, member_id),
        )

    def create_pass(
        self,
        member_id: int,
        token_hash: str,
        now: datetime,
        expires_at: datetime,
        *,
        connection: Connection[dict[str, Any]],
    ) -> None:
        connection.execute(
            """
            INSERT INTO access_passes (member_id, token_hash, created_at, expires_at)
            VALUES (%s, %s, %s, %s)
            """,
            (member_id, token_hash, now, expires_at),
        )

    def find_pass_member(
        self, token_hash: str, *, connection: Connection[dict[str, Any]]
    ) -> dict[str, Any] | None:
        return connection.execute(
            "SELECT member_id FROM access_passes WHERE token_hash = %s",
            (token_hash,),
        ).fetchone()

    def lock_pass(
        self, token_hash: str, *, connection: Connection[dict[str, Any]]
    ) -> dict[str, Any] | None:
        return connection.execute(
            """
            SELECT access_pass_id, member_id, expires_at, consumed_at, invalidated_at
            FROM access_passes WHERE token_hash = %s FOR UPDATE
            """,
            (token_hash,),
        ).fetchone()

    def consume_pass(
        self, pass_id: int, now: datetime, *, connection: Connection[dict[str, Any]]
    ) -> None:
        connection.execute(
            "UPDATE access_passes SET consumed_at = %s WHERE access_pass_id = %s",
            (now, pass_id),
        )

    def create_check_in(
        self,
        pass_id: int,
        membership_id: int,
        employee_id: int,
        now: datetime,
        *,
        connection: Connection[dict[str, Any]],
    ) -> dict[str, Any]:
        try:
            row = connection.execute(
                """
                INSERT INTO check_ins (access_pass_id, membership_id, employee_id, checked_in_at)
                VALUES (%s, %s, %s, %s)
                RETURNING check_in_id, membership_id, employee_id, checked_in_at
                """,
                (pass_id, membership_id, employee_id, now),
            ).fetchone()
        except ForeignKeyViolation as exc:
            if exc.diag.constraint_name == "check_ins_employee_fk":
                raise InvalidTokenError(
                    "Authenticated employee no longer exists"
                ) from exc
            raise
        if row is None:
            raise RuntimeError("Check-in insert returned no row")
        return row


access_repository = AccessRepository()
