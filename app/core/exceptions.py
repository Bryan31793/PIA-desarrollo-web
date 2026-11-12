class DomainError(Exception):
    """Base of all domain exceptions"""

    def __init__(self, message: str | None = None):
        self.message = message or self.default_message
        super().__init__(self.message)

    default_message = "Domain Error"


# --- Autenthication ---


class AuthError(DomainError):
    default_message = "Auth Error"


class InvalidCredentialsError(AuthError):
    default_message = "Invalid Credentials"


class TokenExpiredError(AuthError):
    default_message = "Token expired"


class InvalidTokenError(AuthError):
    default_message = "Invalid Token"


class MemberEmailAlreadyExistsError(DomainError):
    default_message = "Email is already registered"


class StorageUnavailableError(DomainError):
    default_message = "Storage is temporarily unavailable"


class PermissionDeniedError(DomainError):
    default_message = "Insufficient permissions"


class MemberNotFoundError(DomainError):
    default_message = "Member not found"


class PlanNotFoundError(DomainError):
    default_message = "Plan not found"


class MembershipOverlapError(DomainError):
    default_message = "Membership dates overlap an existing membership"


class InvalidMembershipDatesError(DomainError):
    default_message = "Membership end_date must be after start_date"


class MembershipDateOutOfRangeError(DomainError):
    default_message = "Membership dates are outside the supported date range"


class InvalidPlanPriceError(DomainError):
    default_message = "Plan price must be greater than zero"


class InactiveMemberError(PermissionDeniedError):
    default_message = "Member account is inactive"


class ActiveMembershipRequiredError(PermissionDeniedError):
    default_message = "An active membership is required"


class AccessPassUnavailableError(DomainError):
    default_message = "Access pass is invalid, expired, or already used"


class DailyCheckInLimitError(DomainError):
    default_message = "Member has already checked in today"


class PlanNameAlreadyExistsError(DomainError):
    default_message = "Plan name is already registered"


class EmployeeEmailAlreadyExistsError(DomainError):
    default_message = "Employee email is already registered"


class EmployeeRoleNotConfiguredError(DomainError):
    default_message = "Employee role is not configured"
