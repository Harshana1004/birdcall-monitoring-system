import math
import uuid
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    Query,
)
from sqlalchemy import (
    func,
    select,
)
from sqlalchemy.ext.asyncio import (
    AsyncSession,
)

from src.api.schemas import (
    DetectionResponse,
    DetectionSummaryResponse,
    ErrorResponse,
    PaginatedResponse,
    PaginationMetadata,
)
from src.core.exceptions import (
    DetectionNotFoundError,
)
from src.database import get_db
from src.models import Detection


router = APIRouter(
    prefix="/api/v1/detections",
    tags=["Detections"],
)


# ============================================================
# Database dependency
# ============================================================


DatabaseSession = Annotated[
    AsyncSession,
    Depends(get_db),
]


# ============================================================
# List detections
# ============================================================


@router.get(
    "",
    response_model=PaginatedResponse[
        DetectionSummaryResponse
    ],
)
async def list_detections(
    session: DatabaseSession,
    page: Annotated[
        int,
        Query(
            ge=1,
            description="Page number.",
        ),
    ] = 1,
    page_size: Annotated[
        int,
        Query(
            ge=1,
            le=100,
            description=(
                "Number of detections returned per page."
            ),
        ),
    ] = 20,
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
    """
    Return a paginated list of BirdNET detections.
    """

    conditions = []

    # --------------------------------------------------------
    # Optional filters
    # --------------------------------------------------------

    if recording_id is not None:
        conditions.append(
            Detection.recording_id
            == recording_id
        )

    if minimum_confidence is not None:
        conditions.append(
            Detection.confidence
            >= minimum_confidence
        )

    if scientific_name is not None:
        normalized_name = (
            scientific_name.strip()
        )

        if normalized_name:
            conditions.append(
                func.lower(
                    Detection.scientific_name
                )
                == normalized_name.lower()
            )

    # --------------------------------------------------------
    # Count matching detections
    # --------------------------------------------------------

    count_statement = select(
        func.count(
            Detection.id
        )
    )

    if conditions:
        count_statement = (
            count_statement.where(
                *conditions
            )
        )

    total_items = (
        await session.scalar(
            count_statement
        )
    ) or 0

    # --------------------------------------------------------
    # Retrieve requested page
    # --------------------------------------------------------

    offset = (
        page - 1
    ) * page_size

    statement = (
        select(Detection)
        .order_by(
            Detection.created_at.desc()
        )
        .offset(offset)
        .limit(page_size)
    )

    if conditions:
        statement = statement.where(
            *conditions
        )

    result = await session.execute(
        statement
    )

    detections = (
        result.scalars()
        .all()
    )

    total_pages = (
        math.ceil(
            total_items
            / page_size
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


# ============================================================
# Get one detection
# ============================================================


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
    """
    Return one BirdNET detection by UUID.
    """

    detection = await session.get(
        Detection,
        detection_id,
    )

    if detection is None:
        raise DetectionNotFoundError()

    return DetectionResponse.model_validate(
        detection
    )