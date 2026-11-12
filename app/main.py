from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.concurrency import run_in_threadpool

from app.infrastructure.database import db
from app.routers.access import router as access_router
from app.routers.auth import router
from app.routers.employees import router as employees_router
from app.routers.error_handlers import register_error_handlers
from app.routers.members import router as members_router
from app.routers.memberships import router as memberships_router
from app.routers.plans import router as plans_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    db.open_pool()
    try:
        yield
    finally:
        await run_in_threadpool(db.close_pool)


app = FastAPI(
    title="PIA desarrollo web",
    lifespan=lifespan,
    description="CRUD de un gym",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

register_error_handlers(app)
app.include_router(router)
app.include_router(members_router)
app.include_router(memberships_router)
app.include_router(access_router)
app.include_router(plans_router)
app.include_router(employees_router)
