from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.core.exceptions import AuthError, DomainError


async def domain_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Translate domain errors without coupling the domain to HTTP."""
    if not isinstance(exc, DomainError):
        raise exc

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

