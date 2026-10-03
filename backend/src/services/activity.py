"""
Read-side queries for device activity: counts, species summaries,
daily activity and detection feeds with real-world timestamps.

Every function takes a SQL condition on Recording (or None for "all
recordings") so callers decide the scope -- one device, the devices a
user owns, or everything for an admin.
"""

import uuid
from dataclasses import dataclass
from datetime import (
    date,
    datetime,
    timedelta,
)
from zoneinfo import ZoneInfo

from sqlalchemy import (
    ColumnElement,
    func,
    select,
)
from sqlalchemy.ext.asyncio import (
    AsyncSession,
)

from src.api.schemas import (
    DailyActivity,
    DetectionFeedItem,
    SpeciesCount,
    TimelineDetection,
    TimelineRecording,
)
from src.core.config import settings
from src.models import (
    Detection,
    Device,
    Recording,
)


def _where(
    condition: ColumnElement[bool] | None,
) -> list[ColumnElement[bool]]:
    return [] if condition is None else [condition]


def detected_at(
    recording_recorded_at: datetime,
    start_time_seconds: float,
) -> datetime:
    """
    Real-world time of a detection: ROI start + BirdNET offset.
    """

    return recording_recorded_at + timedelta(
        seconds=start_time_seconds
    )


# ============================================================
# Per-device counters
# ============================================================


@dataclass
class DeviceStats:
    recording_count: int = 0
    detection_count: int = 0
    last_recording_at: datetime | None = None


async def device_stats(
    session: AsyncSession,
    device_ids: list[uuid.UUID],
) -> dict[uuid.UUID, DeviceStats]:
    stats = {
        device_id: DeviceStats()
        for device_id in device_ids
    }

    if not device_ids:
        return stats

    recordings = await session.execute(
        select(
            Recording.device_id,
            func.count(Recording.id),
            func.max(Recording.recorded_at),
        )
        .where(
            Recording.device_id.in_(device_ids)
        )
        .group_by(
            Recording.device_id
        )
    )

    for device_id, count, last in recordings.all():
        stats[device_id].recording_count = count
        stats[device_id].last_recording_at = last

    detections = await session.execute(
        select(
            Recording.device_id,
            func.count(Detection.id),
        )
        .join(
            Detection,
            Detection.recording_id == Recording.id,
        )
        .where(
            Recording.device_id.in_(device_ids)
        )
        .group_by(
            Recording.device_id
        )
    )

    for device_id, count in detections.all():
        stats[device_id].detection_count = count

    return stats


# ============================================================
# Totals
# ============================================================


async def count_recordings(
    session: AsyncSession,
    condition: ColumnElement[bool] | None,
    *,
    since: datetime | None = None,
) -> int:
    conditions = _where(condition)

    if since is not None:
        conditions.append(
            Recording.recorded_at >= since
        )

    return (
        await session.scalar(
            select(
                func.count(Recording.id)
            ).where(*conditions)
        )
    ) or 0


async def count_detections(
    session: AsyncSession,
    condition: ColumnElement[bool] | None,
    *,
    since: datetime | None = None,
    distinct_species: bool = False,
) -> int:
    conditions = _where(condition)

    if since is not None:
        conditions.append(
            Recording.recorded_at >= since
        )

    counted = (
        func.count(
            func.distinct(Detection.scientific_name)
        )
        if distinct_species
        else func.count(Detection.id)
    )

    return (
        await session.scalar(
            select(counted)
            .select_from(Detection)
            .join(
                Recording,
                Detection.recording_id == Recording.id,
            )
            .where(*conditions)
        )
    ) or 0


async def recording_time_range(
    session: AsyncSession,
    condition: ColumnElement[bool] | None,
) -> tuple[datetime | None, datetime | None]:
    row = (
        await session.execute(
            select(
                func.min(Recording.recorded_at),
                func.max(Recording.recorded_at),
            ).where(*_where(condition))
        )
    ).one()

    return row[0], row[1]


# ============================================================
# Species and daily activity
# ============================================================


async def top_species(
    session: AsyncSession,
    condition: ColumnElement[bool] | None,
    *,
    limit: int = 10,
) -> list[SpeciesCount]:
    count = func.count(Detection.id)

    result = await session.execute(
        select(
            Detection.scientific_name,
            func.min(Detection.common_name),
            count,
            func.max(Detection.confidence),
            func.max(Recording.recorded_at),
        )
        .join(
            Recording,
            Detection.recording_id == Recording.id,
        )
        .where(*_where(condition))
        .group_by(
            Detection.scientific_name
        )
        .order_by(
            count.desc(),
            Detection.scientific_name.asc(),
        )
        .limit(limit)
    )

    return [
        SpeciesCount(
            scientific_name=scientific_name,
            common_name=common_name,
            detection_count=detection_count,
            max_confidence=float(max_confidence),
            last_detected_at=last_detected_at,
        )
        for (
            scientific_name,
            common_name,
            detection_count,
            max_confidence,
            last_detected_at,
        ) in result.all()
    ]


async def daily_activity(
    session: AsyncSession,
    condition: ColumnElement[bool] | None,
    *,
    days: int = 30,
) -> list[DailyActivity]:
    """
    One entry per calendar day (DEFAULT_TIMEZONE) for the last
    `days` days, oldest first, including empty days.
    """

    zone = ZoneInfo(
        settings.default_timezone
    )
    today = datetime.now(zone).date()
    first_day = today - timedelta(days=days - 1)
    since = datetime.combine(
        first_day,
        datetime.min.time(),
        tzinfo=zone,
    )

    day_expr = func.date(
        func.timezone(
            settings.default_timezone,
            Recording.recorded_at,
        )
    )

    conditions = _where(condition) + [
        Recording.recorded_at >= since
    ]

    recordings_by_day: dict[date, int] = {
        day: count
        for day, count in (
            await session.execute(
                select(
                    day_expr,
                    func.count(Recording.id),
                )
                .where(*conditions)
                .group_by(day_expr)
            )
        ).all()
    }

    detections_by_day: dict[date, int] = {
        day: count
        for day, count in (
            await session.execute(
                select(
                    day_expr,
                    func.count(Detection.id),
                )
                .select_from(Detection)
                .join(
                    Recording,
                    Detection.recording_id == Recording.id,
                )
                .where(*conditions)
                .group_by(day_expr)
            )
        ).all()
    }

    return [
        DailyActivity(
            day=day,
            recording_count=recordings_by_day.get(day, 0),
            detection_count=detections_by_day.get(day, 0),
        )
        for day in (
            first_day + timedelta(days=offset)
            for offset in range(days)
        )
    ]


# ============================================================
# Timelines and feeds
# ============================================================


async def timeline_for_recordings(
    session: AsyncSession,
    recordings: list[Recording],
    *,
    minimum_confidence: float | None = None,
) -> list[TimelineRecording]:
    """
    Attach each recording's detections (with real timestamps).
    """

    by_recording: dict[uuid.UUID, list[TimelineDetection]] = {
        recording.id: []
        for recording in recordings
    }

    if recordings:
        conditions = [
            Detection.recording_id.in_(
                list(by_recording)
            )
        ]

        if minimum_confidence is not None:
            conditions.append(
                Detection.confidence >= minimum_confidence
            )

        recorded_at = {
            recording.id: recording.recorded_at
            for recording in recordings
        }

        result = await session.execute(
            select(Detection)
            .where(*conditions)
            .order_by(
                Detection.start_time_seconds.asc(),
                Detection.confidence.desc(),
            )
        )

        for detection in result.scalars().all():
            by_recording[detection.recording_id].append(
                TimelineDetection(
                    id=detection.id,
                    scientific_name=detection.scientific_name,
                    common_name=detection.common_name,
                    confidence=detection.confidence,
                    start_time_seconds=detection.start_time_seconds,
                    end_time_seconds=detection.end_time_seconds,
                    detected_at=detected_at(
                        recorded_at[detection.recording_id],
                        detection.start_time_seconds,
                    ),
                )
            )

    return [
        TimelineRecording(
            id=recording.id,
            device_id=recording.device_id,
            capture_session_id=recording.capture_session_id,
            snippet_sequence=recording.snippet_sequence,
            recorded_at=recording.recorded_at,
            uploaded_at=recording.uploaded_at,
            duration_seconds=recording.duration_seconds,
            roi_start_seconds=recording.roi_start_seconds,
            roi_end_seconds=recording.roi_end_seconds,
            processing_status=recording.processing_status,
            processing_error=recording.processing_error,
            detections=by_recording[recording.id],
        )
        for recording in recordings
    ]


def detection_feed_statement(
    condition: ColumnElement[bool] | None,
):
    """
    SELECT (Detection, Recording, Device) rows, newest first.
    """

    return (
        select(
            Detection,
            Recording,
            Device,
        )
        .join(
            Recording,
            Detection.recording_id == Recording.id,
        )
        .join(
            Device,
            Recording.device_id == Device.id,
        )
        .where(*_where(condition))
        .order_by(
            Recording.recorded_at.desc(),
            Detection.start_time_seconds.desc(),
            Detection.confidence.desc(),
        )
    )


def feed_item(
    detection: Detection,
    recording: Recording,
    device: Device,
) -> DetectionFeedItem:
    return DetectionFeedItem(
        id=detection.id,
        scientific_name=detection.scientific_name,
        common_name=detection.common_name,
        confidence=detection.confidence,
        start_time_seconds=detection.start_time_seconds,
        end_time_seconds=detection.end_time_seconds,
        detected_at=detected_at(
            recording.recorded_at,
            detection.start_time_seconds,
        ),
        recording_id=recording.id,
        recording_duration_seconds=recording.duration_seconds,
        device_id=device.id,
        device_code=device.device_code,
        device_name=device.name,
    )
