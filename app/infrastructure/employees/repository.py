from typing import Any

from psycopg.errors import UniqueViolation

from app.core.exceptions import (
    EmployeeEmailAlreadyExistsError,
    EmployeeRoleNotConfiguredError,
)
from app.infrastructure.database.db import get_connection


class EmployeeRepository:
    def create(
        self, name: str, email: str, password_hash: str, role_name: str
    ) -> dict[str, Any]:
        try:
            with get_connection() as connection:
                row = connection.execute(
                    """
                    INSERT INTO employees (name, email, password_hash, role_id)
                    SELECT %s, %s, %s, role_id FROM roles WHERE name = %s
                    RETURNING employee_id, name, email, is_active, created_at
                    """,
                    (name, email, password_hash, role_name),
                ).fetchone()
                if row is None:
                    raise EmployeeRoleNotConfiguredError()
                return row
        except UniqueViolation as exc:
            if exc.diag.constraint_name == "employees_email_key":
                raise EmployeeEmailAlreadyExistsError() from exc
            raise

    def find_credentials_by_email(self, email: str) -> dict[str, Any] | None:
        with get_connection() as connection:
            return connection.execute(
                """
                SELECT e.employee_id, e.password_hash, e.is_active, r.name AS role
                FROM employees AS e
                JOIN roles AS r ON r.role_id = e.role_id
                WHERE e.email = %s
                """,
                (email,),
            ).fetchone()

    def find_identity_by_id(self, employee_id: int) -> dict[str, Any] | None:
        with get_connection() as connection:
            return connection.execute(
                """
                SELECT e.employee_id, e.is_active, r.name AS role
                FROM employees AS e
                JOIN roles AS r ON r.role_id = e.role_id
                WHERE e.employee_id = %s
                """,
                (employee_id,),
            ).fetchone()


employee_repository = EmployeeRepository()
