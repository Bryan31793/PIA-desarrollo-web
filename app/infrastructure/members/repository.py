from typing import Any

from psycopg.errors import UniqueViolation

from app.core.exceptions import MemberEmailAlreadyExistsError
from app.infrastructure.database.db import get_connection


class MemberRepository:
    def find_credentials_by_email(self, email: str) -> dict[str, Any] | None:
        with get_connection() as connection:
            return connection.execute(
                """
                SELECT member_id, password_hash, is_active
                FROM members
                WHERE email = %s
                """,
                (email,),
            ).fetchone()

    def find_identity_by_id(self, member_id: int) -> dict[str, Any] | None:
        with get_connection() as connection:
            return connection.execute(
                """
                SELECT member_id, is_active
                FROM members
                WHERE member_id = %s
                """,
                (member_id,),
            ).fetchone()

    def create(self, name: str, email: str, password_hash: str) -> dict[str, Any]:
        try:
            with get_connection() as connection:
                row = connection.execute(
                    """
                    INSERT INTO members (name, email, password_hash)
                    VALUES (%s, %s, %s)
                    RETURNING member_id, name, email, is_active, created_at
                    """,
                    (name, email, password_hash),
                ).fetchone()
                if row is None:
                    raise RuntimeError("Member insert returned no row")
                return row
        except UniqueViolation as exc:
            if exc.diag.constraint_name == "members_email_key":
                raise MemberEmailAlreadyExistsError() from exc
            raise


member_repository = MemberRepository()
