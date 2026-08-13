from collections.abc import (
    AsyncIterator,
)
from contextlib import (
    asynccontextmanager,
)

from fastapi import (
    FastAPI,
    Response,
    status,
)

from fastapi.middleware.cors import (
    CORSMiddleware,
)

from src.api import (
    detections_router,
    devices_router,
    recordings_router,
)
from src.api.exception_handlers import (
    register_exception_handlers,
)
from src.core.config import settings
from src.database import (
    check_database_connection,
    close_database_connection,
)


# ============================================================
# Application lifecycle
# ============================================================


@asynccontextmanager
async def lifespan(
    app: FastAPI,
) -> AsyncIterator[
    None
]:
    """
    Application startup and shutdown lifecycle.
    """

    # --------------------------------------------------------
    # Create required storage directories
    # --------------------------------------------------------

    settings.audio_storage_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    settings.demo_storage_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    # --------------------------------------------------------
    # Verify PostgreSQL
    # --------------------------------------------------------

    database_available = (
        await check_database_connection()
    )

    if not database_available:
        raise RuntimeError(
            "Unable to connect to the PostgreSQL database."
        )

    yield

    # --------------------------------------------------------
    # Shutdown
    # --------------------------------------------------------

    await close_database_connection()


# ============================================================
# FastAPI application
# ============================================================


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


# ============================================================
# CORS
# ============================================================


app.add_middleware(
    CORSMiddleware,
    allow_origins=(
        settings.cors_origins
    ),
    allow_credentials=True,
    allow_methods=[
        "*"
    ],
    allow_headers=[
        "*"
    ],
)


# ============================================================
# Exception handlers
# ============================================================


register_exception_handlers(
    app
)


# ============================================================
# API routers
# ============================================================


app.include_router(
    devices_router
)

app.include_router(
    recordings_router
)

app.include_router(
    detections_router
)


# ============================================================
# System endpoints
# ============================================================


@app.get(
    "/health",
    tags=["System"],
)
async def health_check(
) -> dict[
    str,
    str,
]:
    """
    Verify that the FastAPI application is running.
    """

    return {
        "status": "healthy",
        "environment": (
            settings.app_environment
        ),
        "version": (
            settings.app_version
        ),
    }


@app.get(
    "/ready",
    tags=["System"],
)
async def readiness_check(
    response: Response,
) -> dict[
    str,
    str,
]:
    """
    Verify that required backend services are available.
    """

    database_available = (
        await check_database_connection()
    )

    if not database_available:
        response.status_code = (
            status.HTTP_503_SERVICE_UNAVAILABLE
        )

        return {
            "status": "not_ready",
            "database": "unavailable",
        }

    return {
        "status": "ready",
        "database": "available",
    }


    #uvicorn src.server:app --reload