from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr, field_validator

from app.core.roles import Role

EmployeeRole = Literal[Role.ADMIN, Role.STAFF]


class EmployeeRegistration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    email: EmailStr = Field(max_length=254)
    password: SecretStr = Field(min_length=8, max_length=128)
    role: EmployeeRole

    @field_validator("name", mode="before")
    @classmethod
    def trim_name(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class EmployeeResponse(BaseModel):
    employee_id: int
    name: str
    email: EmailStr
    role: EmployeeRole
    is_active: bool
    created_at: datetime
