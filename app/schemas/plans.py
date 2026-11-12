from decimal import Decimal
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

PlanName = Annotated[str, Field(min_length=1, max_length=50)]
PlanPrice = Annotated[
    Decimal,
    Field(
        gt=0,
        le=Decimal("99999999.99"),
        max_digits=10,
        decimal_places=2,
        allow_inf_nan=False,
    ),
]
PlanDuration = Annotated[int, Field(strict=True, gt=0, le=2**31 - 1)]


class PlanCreation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: PlanName
    price: PlanPrice
    duration_days: PlanDuration

    @field_validator("name", mode="before")
    @classmethod
    def trim_name(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class PlanPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: PlanName | None = None
    price: PlanPrice | None = None
    duration_days: PlanDuration | None = None

    @field_validator("name", mode="before")
    @classmethod
    def trim_name(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def require_non_null_changes(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("At least one plan field is required")
        if any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("Plan fields cannot be null")
        return self


class PlanResponse(BaseModel):
    plan_id: int
    name: str
    price: Decimal
    duration_days: int
