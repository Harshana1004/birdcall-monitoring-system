from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.exception_handlers import register_exception_handlers
from api.routes import (
    devices_router,
    recordings_router,
    detections_router,
)
from core.config import settings
from core.db import (
    check_database_connection,
    close_database_connection,
)


@asynccontextmanager
async def lifespan(
    app: FastAPI,
) -> AsyncIterator[None]:
    """Application startup and shutdown tasks."""

    settings.audio_storage_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    database_available = await check_database_connection()

    if not database_available:
        raise RuntimeError(
            "Unable to connect to the PostgreSQL database."
        )

    yield

    await close_database_connection()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "Backend API for the BirdCall Monitoring System."
    ),
    debug=settings.debug,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


register_exception_handlers(app)

app.include_router(devices_router)
app.include_router(recordings_router)
app.include_router(detections_router)


@app.get(
    "/health",
    tags=["System"],
)
async def health_check() -> dict[str, str]:
    """
    Verify that the FastAPI application is running.
    """

    return {
        "status": "healthy",
        "environment": settings.app_environment,
        "version": settings.app_version,
    }


@app.get(
    "/ready",
    tags=["System"],
)
async def readiness_check() -> dict[str, str]:
    """
    Verify that required backend services are available.
    """

    database_available = await check_database_connection()

    if not database_available:
        return {
            "status": "not_ready",
            "database": "unavailable",
        }

    return {
        "status": "ready",
        "database": "available",
    }


    #uvicorn src.server:app --reload