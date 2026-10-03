import math
import uuid
from datetime import datetime
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    Query,
)
from sqlalchemy import (
    and_,
    func,
    or_,
    select,
)
from sqlalchemy.ext.asyncio import (
    AsyncSession,
)

from src.api.access import (
    get_visible_recording,
    recording_visibility,
)
from src.api.auth import CurrentUser
from src.api.schemas import (
    DetectionFeedItem,
    DetectionResponse,
    ErrorResponse,
    PaginatedResponse,
    PaginationMetadata,
)
from src.core.config import settings
from src.core.exceptions import (
    DetectionNotFoundError,
    RecordingNotFoundError,
)
from src.database import get_db
from src.models import (
    Detection,
    Device,
    Recording,
)
from src.services import activity


router = APIRouter(
    prefix="/api/v1/detections",
    tags=["Detections"],
)


DatabaseSession = Annotated[
    AsyncSession,
    Depends(get_db),
]


# ============================================================
# Detection feed
# ============================================================


@router.get(
    "",
    response_model=PaginatedResponse[DetectionFeedItem],
)
async def list_detections(
    user: CurrentUser,
    session: DatabaseSession,
    page: Annotated[int, Query(ge=1, description="Page number.")] = 1,
    page_size: Annotated[
        int,
        Query(ge=1, le=100, description="Detections per page."),
    ] = 25,
    device_id: Annotated[
        uuid.UUID | None,
        Query(description="Only detections from this device."),
    ] = None,
    recording_id: Annotated[
        uuid.UUID | None,
        Query(description="Only detections from this recording."),
    ] = None,
    date_from: Annotated[
        datetime | None,
        Query(description="ROIs recorded at or after this time."),
    ] = None,
    date_to: Annotated[
        datetime | None,
        Query(description="ROIs recorded before this time."),
    ] = None,
    minimum_confidence: Annotated[
        float | None,
        Query(ge=0, le=1, description="Minimum BirdNET confidence."),
    ] = None,
    species: Annotated[
        str | None,
        Query(
            min_length=1,
            max_length=180,
            description="Match common or scientific name (partial).",
        ),
    ] = None,
    include_manual: Annotated[
        bool,
        Query(description="Also include your manual-analysis uploads."),
    ] = False,
) -> PaginatedResponse[DetectionFeedItem]:
    """
    BirdNET detections you can see, newest first, each with its
    real-world time, device and recording.
    """

    conditions = []

    visibility = recording_visibility(user)
    if visibility is not None:
        conditions.append(visibility)

    if not include_manual:
        conditions.append(
            Device.device_code != settings.manual_upload_device_code
        )

    if device_id is not None:
        conditions.append(Recording.device_id == device_id)

    if recording_id is not None:
        conditions.append(Detection.recording_id == recording_id)

    if date_from is not None:
        conditions.append(Recording.recorded_at >= date_from)

    if date_to is not None:
        conditions.append(Recording.recorded_at < date_to)

    if minimum_confidence is not None:
        conditions.append(Detection.confidence >= minimum_confidence)

    if species and species.strip():
        pattern = f"%{species.strip()}%"
        conditions.append(
            or_(
                Detection.common_name.ilike(pattern),
                Detection.scientific_name.ilike(pattern),
            )
        )

    condition = and_(*conditions) if conditions else None

    total_items = (
        await session.scalar(
            select(func.count(Detection.id))
            .select_from(Detection)
            .join(Recording, Detection.recording_id == Recording.id)
            .join(Device, Recording.device_id == Device.id)
            .where(*conditions)
        )
    ) or 0

    result = await session.execute(
        activity.detection_feed_statement(condition)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    return PaginatedResponse[DetectionFeedItem](
        items=[
            activity.feed_item(detection, recording, device)
            for detection, recording, device in result.all()
        ],
        pagination=PaginationMetadata(
            page=page,
            page_size=page_size,
            total_items=total_items,
            total_pages=(
                math.ceil(total_items / page_size)
                if total_items
                else 0
            ),
        ),
    )


# ============================================================
# One detection
# ============================================================


@router.get(
    "/{detection_id}",
    response_model=DetectionResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Detection not found."},
    },
)
async def get_detection(
    detection_id: uuid.UUID,
    user: CurrentUser,
    session: DatabaseSession,
) -> DetectionResponse:
    detection = await session.get(Detection, detection_id)

    if detection is None:
        raise DetectionNotFoundError()

    try:
        await get_visible_recording(session, user, detection.recording_id)

    except RecordingNotFoundError as exception:
        raise DetectionNotFoundError() from exception

    return DetectionResponse.model_validate(detection)
