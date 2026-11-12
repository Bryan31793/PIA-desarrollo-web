from datetime import date
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.payments import PaymentResponse

# Rango de BIGINT de PostgreSQL; la existencia de cada ID se comprueba en la base.
DatabaseId = Annotated[int, Field(strict=True, ge=-(2**63), le=2**63 - 1)]


class MembershipRegistration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    member_id: DatabaseId
    plan_id: DatabaseId


class MembershipResponse(BaseModel):
    membership_id: int
    member_id: int
    plan_id: int
    start_date: date
    end_date: date
    payment: PaymentResponse


class CurrentMembershipResponse(BaseModel):
    membership_id: int
    plan_id: int
    plan_name: str
    start_date: date
    end_date: date


class MembershipStatusResponse(BaseModel):
    has_active_plan: bool
    membership: CurrentMembershipResponse | None
