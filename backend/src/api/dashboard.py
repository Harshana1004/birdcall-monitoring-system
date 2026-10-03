from datetime import (
    datetime,
    timedelta,
    timezone,
)
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    Query,
)
from sqlalchemy import (
    and_,
    func,
    select,
)
from sqlalchemy.ext.asyncio import (
    AsyncSession,
)

from src.api.auth import CurrentUser
from src.api.schemas import DashboardResponse
from src.core.config import settings
from src.database import get_db
from src.models import (
    Device,
    Recording,
)
from src.services import activity


router = APIRouter(
    prefix="/api/v1/dashboard",
    tags=["Dashboard"],
)


DatabaseSession = Annotated[
    AsyncSession,
    Depends(get_db),
]


@router.get(
    "",
    response_model=DashboardResponse,
)
async def get_dashboard(
    user: CurrentUser,
    session: DatabaseSession,
    days: Annotated[
        int,
        Query(ge=1, le=90, description="Days of daily activity."),
    ] = 14,
    recent: Annotated[
        int,
        Query(ge=1, le=50, description="Recent detections to include."),
    ] = 10,
) -> DashboardResponse:
    """
    Overview of your devices (admins: every device). Manual-analysis
    uploads are not included.
    """

    not_manual = (
        Device.device_code != settings.manual_upload_device_code
    )

    device_condition = (
        not_manual
        if user.is_admin
        else and_(not_manual, Device.owner_id == user.id)
    )

    scope = Recording.device_id.in_(
        select(Device.id).where(device_condition)
    )

    since_24h = datetime.now(timezone.utc) - timedelta(hours=24)
    _, last_recording_at = await activity.recording_time_range(
        session, scope
    )

    recent_rows = await session.execute(
        activity.detection_feed_statement(scope).limit(recent)
    )

    return DashboardResponse(
        device_count=(
            await session.scalar(
                select(func.count(Device.id)).where(device_condition)
            )
        )
        or 0,
        active_device_count=(
            await session.scalar(
                select(func.count(Device.id)).where(
                    device_condition,
                    Device.is_active.is_(True),
                )
            )
        )
        or 0,
        recording_count=await activity.count_recordings(session, scope),
        recordings_last_24h=await activity.count_recordings(
            session, scope, since=since_24h
        ),
        detection_count=await activity.count_detections(session, scope),
        detections_last_24h=await activity.count_detections(
            session, scope, since=since_24h
        ),
        species_count=await activity.count_detections(
            session, scope, distinct_species=True
        ),
        last_recording_at=last_recording_at,
        top_species=await activity.top_species(session, scope, limit=8),
        daily_activity=await activity.daily_activity(
            session, scope, days=days
        ),
        recent_detections=[
            activity.feed_item(detection, recording, device)
            for detection, recording, device in recent_rows.all()
        ],
    )
