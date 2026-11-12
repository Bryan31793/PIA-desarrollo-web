from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.core.exceptions import (
    AccessPassUnavailableError,
    AuthError,
    DailyCheckInLimitError,
    DomainError,
    EmployeeEmailAlreadyExistsError,
    EmployeeRoleNotConfiguredError,
    InvalidMembershipDatesError,
    InvalidPlanPriceError,
    MemberEmailAlreadyExistsError,
    MemberNotFoundError,
    MembershipDateOutOfRangeError,
    MembershipOverlapError,
    PermissionDeniedError,
    PlanNameAlreadyExistsError,
    PlanNotFoundError,
    StorageUnavailableError,
)


async def domain_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Translate domain errors without coupling the domain to HTTP."""
    if not isinstance(exc, DomainError):
        raise exc

    if isinstance(exc, (MemberNotFoundError, PlanNotFoundError)):
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": exc.message},
        )
    if isinstance(
        exc,
        (
            InvalidMembershipDatesError,
            MembershipDateOutOfRangeError,
            InvalidPlanPriceError,
        ),
    ):
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={"detail": exc.message},
        )
    if isinstance(
        exc,
        (
            MemberEmailAlreadyExistsError,
            MembershipOverlapError,
            AccessPassUnavailableError,
            DailyCheckInLimitError,
            EmployeeEmailAlreadyExistsError,
            EmployeeRoleNotConfiguredError,
            PlanNameAlreadyExistsError,
        ),
    ):
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"detail": exc.message},
        )
    if isinstance(exc, StorageUnavailableError):
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"detail": exc.message},
        )
    if isinstance(exc, PermissionDeniedError):
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"detail": exc.message},
        )
    if isinstance(exc, AuthError):
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"detail": exc.message},
            headers={"WWW-Authenticate": "Bearer"},
        )
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": exc.message},
    )


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(DomainError, domain_error_handler)
