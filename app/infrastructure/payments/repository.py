from decimal import Decimal
from typing import Any

from psycopg import Connection
from psycopg.errors import ForeignKeyViolation

from app.core.exceptions import InvalidTokenError


class PaymentRepository:
    def create(
        self,
        membership_id: int,
        employee_id: int,
        amount: Decimal,
        *,
        connection: Connection[dict[str, Any]],
    ) -> dict[str, Any]:
        """Participa en la transacción del alta; no confirma pagos por separado."""
        try:
            row = connection.execute(
                """
                INSERT INTO payments (membership_id, employee_id, amount)
                VALUES (%s, %s, %s)
                RETURNING payment_id, membership_id, employee_id, amount,
                          currency, paid_at, notes
                """,
                (membership_id, employee_id, amount),
            ).fetchone()
        except ForeignKeyViolation as exc:
            if exc.diag.constraint_name == "payments_employee_fk":
                raise InvalidTokenError(
                    "Authenticated employee no longer exists"
                ) from exc
            raise
        if row is None:
            raise RuntimeError("Payment insert returned no row")
        return row


payment_repository = PaymentRepository()
