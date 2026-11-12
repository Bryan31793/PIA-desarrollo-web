from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, SecretStr


class AccessPassResponse(BaseModel):
    pass_token: str
    expires_at: datetime
    expires_in: int


class CheckInRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pass_token: SecretStr = Field(min_length=43, max_length=43)


class CheckInResponse(BaseModel):
    check_in_id: int
    member_id: int
    member_name: str
    membership_id: int
    employee_id: int
    checked_in_at: datetime
