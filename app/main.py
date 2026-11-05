from fastapi import FastAPI, Request

from app.core.exceptions import AuthError, DomainError
from app.routers.auth import router
from app.routers.error_handlers import domain_error_handler, register_error_handlers
from app.services.auth_service import verify_access_token

app = FastAPI(
    title="PIA desarrollo web",
    description="CRUD de un gym",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

register_error_handlers(app)
app.include_router(router)

@app.middleware("http")
async def require_access_token(request: Request, call_next):
    if request.url.path == "/api" or request.url.path.startswith("/api/"):
        authorization = request.headers.get("Authorization", "")
        parts = authorization.split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            return await domain_error_handler(
                request, AuthError("Bearer access token required")
            )
        try:
            request.state.username = verify_access_token(parts[1])
        except DomainError as exc:
            # Middleware runs outside FastAPI's exception handlers.
            return await domain_error_handler(request, exc)
    return await call_next(request)
