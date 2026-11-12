from fastapi import APIRouter, status

from app.schemas.members import MemberRegistration, MemberResponse
from app.services.member_service import register_member

router = APIRouter(prefix="/auth", tags=["Members"])


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    response_model=MemberResponse,
    responses={
        409: {"description": "Email is already registered"},
        503: {"description": "Storage unavailable"},
    },
)
def register(data: MemberRegistration) -> MemberResponse:
    return register_member(data)
