from contextlib import nullcontext
from decimal import Decimal
from typing import Any

from psycopg import Connection, sql
from psycopg.errors import UniqueViolation

from app.core.exceptions import PlanNameAlreadyExistsError
from app.infrastructure.database.db import get_connection


class PlanRepository:
    def create(self, name: str, price: Decimal, duration_days: int) -> dict[str, Any]:
        try:
            with get_connection() as connection:
                row = connection.execute(
                    """
                    INSERT INTO plans (name, price, duration_days) VALUES (%s, %s, %s)
                    RETURNING plan_id, name, price, duration_days
                    """,
                    (name, price, duration_days),
                ).fetchone()
                if row is None:
                    raise RuntimeError("Plan insert returned no row")
                return row
        except UniqueViolation as exc:
            if exc.diag.constraint_name == "plans_name_key":
                raise PlanNameAlreadyExistsError() from exc
            raise

    def patch(self, plan_id: int, changes: dict[str, Any]) -> dict[str, Any] | None:
        if not changes or not changes.keys() <= {"name", "price", "duration_days"}:
            raise ValueError("Invalid plan update fields")
        assignments = sql.SQL(", ").join(
            sql.SQL("{} = %s").format(sql.Identifier(field)) for field in changes
        )
        query = sql.SQL(
            "UPDATE plans SET {} WHERE plan_id = %s RETURNING plan_id, name, price, duration_days"
        ).format(assignments)
        try:
            with get_connection() as connection:
                return connection.execute(
                    query, (*changes.values(), plan_id)
                ).fetchone()
        except UniqueViolation as exc:
            if exc.diag.constraint_name == "plans_name_key":
                raise PlanNameAlreadyExistsError() from exc
            raise

    def find_by_id(
        self, plan_id: int, *, connection: Connection[dict[str, Any]] | None = None
    ) -> dict[str, Any] | None:
        context = (
            nullcontext(connection) if connection is not None else get_connection()
        )
        with context as active_connection:
            return active_connection.execute(
                """
                SELECT plan_id, duration_days, price
                FROM plans
                WHERE plan_id = %s
                FOR SHARE
                """,
                (plan_id,),
            ).fetchone()


plan_repository = PlanRepository()
