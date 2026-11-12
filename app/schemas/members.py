from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr, field_validator


class MemberRegistration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    email: EmailStr = Field(max_length=254)
    password: SecretStr = Field(min_length=8, max_length=128)

    @field_validator("name", mode="before")
    @classmethod
    def trim_name(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class MemberResponse(BaseModel):
    member_id: int
    name: str
    email: EmailStr
    is_active: bool
    created_at: datetime
