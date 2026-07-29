import uuid

from uuid import UUID

from models.recording import Recording

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.recording import (
    ProcessingStatus,
    Recording,
)


class RecordingRepository:
    """Database operations for ROI recordings."""

    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        self.session = session

    async def create(
        self,
        recording: Recording,
    ) -> Recording:
        self.session.add(recording)

        await self.session.flush()
        await self.session.refresh(recording)

        return recording

    async def get_by_id(
        self,
        recording_id: uuid.UUID,
    ) -> Recording | None:
        statement = select(Recording).where(
            Recording.id == recording_id,
        )

        result = await self.session.execute(statement)

        return result.scalar_one_or_none()

    async def get_by_client_upload_id(
        self,
        *,
        device_id: uuid.UUID,
        client_upload_id: uuid.UUID,
    ) -> Recording | None:
        statement = select(Recording).where(
            Recording.device_id == device_id,
            Recording.client_upload_id == client_upload_id,
        )

        result = await self.session.execute(statement)

        return result.scalar_one_or_none()

    async def get_by_device_and_checksum(
        self,
        *,
        device_id: uuid.UUID,
        checksum_sha256: str,
    ) -> Recording | None:
        statement = select(Recording).where(
            Recording.device_id == device_id,
            Recording.checksum_sha256 == checksum_sha256,
        )

        result = await self.session.execute(statement)

        return result.scalar_one_or_none()

    async def list(
        self,
        *,
        offset: int,
        limit: int,
        device_id: uuid.UUID | None = None,
        capture_session_id: uuid.UUID | None = None,
        processing_status: ProcessingStatus | None = None,
    ) -> list[Recording]:
        statement = select(Recording)

        if device_id is not None:
            statement = statement.where(
                Recording.device_id == device_id,
            )

        if capture_session_id is not None:
            statement = statement.where(
                Recording.capture_session_id
                == capture_session_id,
            )

        if processing_status is not None:
            statement = statement.where(
                Recording.processing_status
                == processing_status,
            )

        statement = (
            statement
            .order_by(
                Recording.recorded_at.desc(),
                Recording.snippet_sequence.asc(),
            )
            .offset(offset)
            .limit(limit)
        )

        result = await self.session.execute(statement)

        return list(result.scalars().all())

    async def count(
        self,
        *,
        device_id: uuid.UUID | None = None,
        capture_session_id: uuid.UUID | None = None,
        processing_status: ProcessingStatus | None = None,
    ) -> int:
        statement = select(
            func.count(Recording.id)
        )

        if device_id is not None:
            statement = statement.where(
                Recording.device_id == device_id,
            )

        if capture_session_id is not None:
            statement = statement.where(
                Recording.capture_session_id
                == capture_session_id,
            )

        if processing_status is not None:
            statement = statement.where(
                Recording.processing_status
                == processing_status,
            )

        result = await self.session.execute(statement)

        return result.scalar_one()

    async def delete(
        self,
        recording: Recording,
    ) -> None:
        await self.session.delete(recording)
        await self.session.flush()