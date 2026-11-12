from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class PaymentResponse(BaseModel):
    payment_id: int
    membership_id: int
    employee_id: int
    amount: Decimal
    currency: str
    paid_at: datetime
    notes: str | None
