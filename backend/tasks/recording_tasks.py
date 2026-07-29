import logging
import uuid

from core.db import AsyncSessionLocal
from services.recording_processing_service import (
    RecordingProcessingService,
)


logger = logging.getLogger(__name__)


async def process_recording_background(
    recording_id: uuid.UUID,
) -> None:
    """
    Process one recording using a fresh database session.

    A new session is required because the request-scoped session
    is closed after FastAPI returns the upload response.
    """

    try:
        async with AsyncSessionLocal() as session:
            service = RecordingProcessingService(
                session=session
            )

            await service.process_recording(
                recording_id
            )

    except Exception:
        logger.exception(
            "Unhandled background processing error "
            "for recording %s.",
            recording_id,
        )