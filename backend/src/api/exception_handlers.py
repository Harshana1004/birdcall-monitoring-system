import logging

from fastapi import (
    FastAPI,
    Request,
)
from fastapi.responses import (
    JSONResponse,
)

from src.core.exceptions import (
    ApplicationError,
)


logger = logging.getLogger(
    __name__
)


async def application_error_handler(
    request: Request,
    exception: ApplicationError,
) -> JSONResponse:
    return JSONResponse(
        status_code=(
            exception.status_code
        ),
        content={
            "error": (
                exception.error_code
            ),
            "message": (
                exception.message
            ),
        },
    )


async def unexpected_error_handler(
    request: Request,
    exception: Exception,
) -> JSONResponse:
    logger.exception(
        "Unhandled error while processing %s %s",
        request.method,
        request.url.path,
    )

    return JSONResponse(
        status_code=500,
        content={
            "error": (
                "internal_server_error"
            ),
            "message": (
                "An unexpected server "
                "error occurred."
            ),
        },
    )


def register_exception_handlers(
    app: FastAPI,
) -> None:
    app.add_exception_handler(
        ApplicationError,
        application_error_handler,
    )

    app.add_exception_handler(
        Exception,
        unexpected_error_handler,
    )