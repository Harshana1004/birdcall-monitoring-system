import uuid
from collections.abc import Sequence

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.detection import Detection


class DetectionRepository:
    """
    Database access for BirdNET detections.

    Repository methods do not commit transactions. Transaction
    boundaries are controlled by the service layer.
    """

    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        self.session = session

    async def create_many(
        self,
        detections: Sequence[Detection],
    ) -> list[Detection]:
        if not detections:
            return []

        self.session.add_all(
            detections
        )

        await self.session.flush()

        return list(
            detections
        )

    async def get_by_id(
        self,
        detection_id: uuid.UUID,
    ) -> Detection | None:
        statement = (
            select(Detection)
            .where(
                Detection.id == detection_id
            )
        )

        result = await self.session.execute(
            statement
        )

        return result.scalar_one_or_none()

    async def list_detections(
        self,
        *,
        offset: int,
        limit: int,
        recording_id: uuid.UUID | None = None,
        minimum_confidence: float | None = None,
        scientific_name: str | None = None,
    ) -> list[Detection]:
        statement = select(
            Detection
        )

        if recording_id is not None:
            statement = statement.where(
                Detection.recording_id
                == recording_id
            )

        if minimum_confidence is not None:
            statement = statement.where(
                Detection.confidence
                >= minimum_confidence
            )

        if scientific_name is not None:
            statement = statement.where(
                Detection.scientific_name.ilike(
                    f"%{scientific_name}%"
                )
            )

        statement = (
            statement
            .order_by(
                Detection.confidence.desc(),
                Detection.start_time_seconds.asc(),
            )
            .offset(offset)
            .limit(limit)
        )

        result = await self.session.execute(
            statement
        )

        return list(
            result.scalars().all()
        )

    async def count_detections(
        self,
        *,
        recording_id: uuid.UUID | None = None,
        minimum_confidence: float | None = None,
        scientific_name: str | None = None,
    ) -> int:
        statement = select(
            func.count(Detection.id)
        )

        if recording_id is not None:
            statement = statement.where(
                Detection.recording_id
                == recording_id
            )

        if minimum_confidence is not None:
            statement = statement.where(
                Detection.confidence
                >= minimum_confidence
            )

        if scientific_name is not None:
            statement = statement.where(
                Detection.scientific_name.ilike(
                    f"%{scientific_name}%"
                )
            )

        result = await self.session.execute(
            statement
        )

        return int(
            result.scalar_one()
        )

    async def get_by_recording_id(
        self,
        recording_id: uuid.UUID,
    ) -> list[Detection]:
        statement = (
            select(Detection)
            .where(
                Detection.recording_id
                == recording_id
            )
            .order_by(
                Detection.start_time_seconds.asc(),
                Detection.confidence.desc(),
            )
        )

        result = await self.session.execute(
            statement
        )

        return list(
            result.scalars().all()
        )

    async def delete_by_recording_id(
        self,
        recording_id: uuid.UUID,
    ) -> None:
        statement = (
            delete(Detection)
            .where(
                Detection.recording_id
                == recording_id
            )
        )

        await self.session.execute(
            statement
        )