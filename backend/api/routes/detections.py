import uuid
from typing import Annotated

from fastapi import (
    APIRouter,
    Query,
)

from api.dependencies import (
    DatabaseSession,
    PageNumber,
    PageSize,
)
from schemas.common import (
    ErrorResponse,
    PaginatedResponse,
)
from schemas.detection import (
    DetectionResponse,
    DetectionSummaryResponse,
)
from services.detection_service import (
    DetectionService,
)


router = APIRouter(
    prefix="/api/v1/detections",
    tags=["Detections"],
)


@router.get(
    "",
    response_model=PaginatedResponse[
        DetectionSummaryResponse
    ],
)
async def list_detections(
    session: DatabaseSession,
    page: PageNumber = 1,
    page_size: PageSize = 20,
    recording_id: Annotated[
        uuid.UUID | None,
        Query(
            description=(
                "Return detections belonging to one "
                "recording."
            ),
        ),
    ] = None,
    minimum_confidence: Annotated[
        float | None,
        Query(
            ge=0,
            le=1,
            description=(
                "Return detections at or above this "
                "confidence."
            ),
        ),
    ] = None,
    scientific_name: Annotated[
        str | None,
        Query(
            min_length=1,
            max_length=255,
            description=(
                "Filter by scientific species name."
            ),
        ),
    ] = None,
) -> PaginatedResponse[
    DetectionSummaryResponse
]:
    service = DetectionService(
        session
    )

    return await service.list_detections(
        page=page,
        page_size=page_size,
        recording_id=recording_id,
        minimum_confidence=minimum_confidence,
        scientific_name=scientific_name,
    )


@router.get(
    "/{detection_id}",
    response_model=DetectionResponse,
    responses={
        404: {
            "model": ErrorResponse,
            "description": (
                "Detection not found."
            ),
        },
    },
)
async def get_detection(
    detection_id: uuid.UUID,
    session: DatabaseSession,
) -> DetectionResponse:
    service = DetectionService(
        session
    )

    return await service.get_detection(
        detection_id
    )