from app.core.passwords import password_hasher
from app.infrastructure.members.repository import member_repository
from app.schemas.members import MemberRegistration, MemberResponse


def register_member(data: MemberRegistration) -> MemberResponse:
    password_hash = password_hasher.hash(data.password.get_secret_value())
    member = member_repository.create(data.name, str(data.email).lower(), password_hash)
    return MemberResponse.model_validate(member)
