from dataclasses import dataclass

from app.core.roles import Role


def parse_subject(subject: str) -> tuple[str, int]:
    """Identifica la tabla y el ID sin colisiones entre tipos de cuenta."""
    kind, separator, account_id = subject.partition(":")
    if (
        kind not in {"member", "employee"}
        or not separator
        or not account_id.isascii()
        or not account_id.isdecimal()
        or account_id.startswith("0")
    ):
        raise ValueError("Invalid account subject")
    identifier = int(account_id)
    if identifier > 2**63 - 1:
        raise ValueError("Invalid account ID")
    return kind, identifier


@dataclass(frozen=True)
class AuthenticatedIdentity:
    subject: str
    role: Role

    def __post_init__(self) -> None:
        kind, _ = parse_subject(self.subject)
        if not isinstance(self.role, Role) or (
            (kind == "member") != (self.role == Role.MEMBER)
        ):
            raise ValueError("Role does not match account type")
