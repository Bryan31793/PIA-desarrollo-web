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

