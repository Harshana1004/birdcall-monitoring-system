import math
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from core.exceptions import (
    DetectionNotFoundError,
)
from repositories.detection_repository import (
    DetectionRepository,
)
from repositories.recording_repository import (
    RecordingRepository,
)
from schemas.common import PaginatedResponse
from schemas.detection import (
    DetectionResponse,
    DetectionSummaryResponse,
)


class DetectionService:
    """
    Application logic for querying BirdNET detections.
    """

    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        self.session = session

        self.detection_repository = (
            DetectionRepository(
                session
            )
        )

        self.recording_repository = (
            RecordingRepository(
                session
            )
        )

    async def get_detection(
        self,
        detection_id: uuid.UUID,
    ) -> DetectionResponse:
        detection = (
            await self.detection_repository.get_by_id(
                detection_id
            )
        )

        if detection is None:
            raise DetectionNotFoundError(
                detection_id
            )

        return DetectionResponse.model_validate(
            detection
        )

    async def list_detections(
        self,
        *,
        page: int,
        page_size: int,
        recording_id: uuid.UUID | None = None,
        minimum_confidence: float | None = None,
        scientific_name: str | None = None,
    ) -> PaginatedResponse[
        DetectionSummaryResponse
    ]:
        offset = (
            page - 1
        ) * page_size

        detections = (
            await self.detection_repository.list_detections(
                offset=offset,
                limit=page_size,
                recording_id=recording_id,
                minimum_confidence=minimum_confidence,
                scientific_name=scientific_name,
            )
        )

        total_items = (
            await self.detection_repository.count_detections(
                recording_id=recording_id,
                minimum_confidence=minimum_confidence,
                scientific_name=scientific_name,
            )
        )

        total_pages = (
            math.ceil(
                total_items / page_size
            )
            if total_items > 0
            else 0
        )

        return PaginatedResponse[
            DetectionSummaryResponse
        ](
            items=[
                DetectionSummaryResponse.model_validate(
                    detection
                )
                for detection in detections
            ],
            pagination=PaginationMetadata(
                page=page,
                page_size=page_size,
                total_items=total_items,
                total_pages=total_pages,
            ),
        )

    async def get_recording_detections(
        self,
        recording_id: uuid.UUID,
    ) -> list[DetectionResponse]:
        recording = (
            await self.recording_repository.get_by_id(
                recording_id
            )
        )

        if recording is None:
            from core.exceptions import (
                RecordingNotFoundError,
            )

            raise RecordingNotFoundError(
                recording_id
            )

        detections = (
            await self.detection_repository
            .get_by_recording_id(
                recording_id
            )
        )

        return [
            DetectionResponse.model_validate(
                detection
            )
            for detection in detections
        ]