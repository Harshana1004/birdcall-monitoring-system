import math
import uuid
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.exceptions import (
    InvalidUploadMetadataError,
    ResourceConflictError,
    ResourceNotFoundError,
)
from models.recording import (
    ProcessingStatus,
    Recording,
)
from repositories.device_repository import DeviceRepository
from repositories.recording_repository import (
    RecordingRepository,
)
from schemas.common import (
    PaginatedResponse,
    PaginationMetadata,
)
from schemas.recording import (
    RecordingSummaryResponse,
    RecordingUploadMetadata,
)
from services.audio_storage_service import (
    AudioStorageService,
    StoredAudioFile,
)


@dataclass(frozen=True)
class RecordingUploadResult:
    """Result of a new upload or an idempotent replay."""

    recording: Recording
    created: bool


class RecordingService:
    """Business logic for ROI snippet uploads and retrieval."""

    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        self.session = session

        self.recording_repository = RecordingRepository(
            session
        )

        self.device_repository = DeviceRepository(
            session
        )

        self.storage_service = AudioStorageService()

    async def upload_recording(
        self,
        *,
        device_id: uuid.UUID,
        upload: UploadFile,
        metadata: RecordingUploadMetadata,
    ) -> RecordingUploadResult:
        device = await self.device_repository.get_by_id(
            device_id
        )

        if device is None:
            raise ResourceNotFoundError(
                f"Device '{device_id}' was not found."
            )

        if not device.is_active:
            raise ResourceConflictError(
                "ROI snippets cannot be uploaded for an "
                "inactive device."
            )

        staged_file: StoredAudioFile | None = None
        finalized_file: StoredAudioFile | None = None

        try:
            staged_file = (
                await self.storage_service.stage_upload(
                    upload
                )
            )

            existing_upload = (
                await self.recording_repository
                .get_by_client_upload_id(
                    device_id=device_id,
                    client_upload_id=(
                        metadata.client_upload_id
                    ),
                )
            )

            if existing_upload is not None:
                if (
                    existing_upload.checksum_sha256
                    != staged_file.checksum_sha256
                ):
                    raise ResourceConflictError(
                        "The client_upload_id has already been "
                        "used for a different audio file."
                    )

                await self.storage_service.delete_file(
                    staged_file.file_path
                )

                return RecordingUploadResult(
                    recording=existing_upload,
                    created=False,
                )

            duplicate_content = (
                await self.recording_repository
                .get_by_device_and_checksum(
                    device_id=device_id,
                    checksum_sha256=(
                        staged_file.checksum_sha256
                    ),
                )
            )

            if duplicate_content is not None:
                raise ResourceConflictError(
                    "An identical audio snippet has already "
                    "been uploaded for this device. Existing "
                    f"recording ID: {duplicate_content.id}."
                )

            self._validate_roi_duration(
                metadata=metadata,
                staged_file=staged_file,
            )

            recording_id = uuid.uuid4()

            finalized_file = (
                await self.storage_service.finalize_upload(
                    staged_file,
                    device_id=device_id,
                    recording_id=recording_id,
                )
            )

            recorded_at = (
                metadata.capture_started_at
                + timedelta(
                    seconds=metadata.roi_start_seconds,
                )
            )

            recording = Recording(
                id=recording_id,
                device_id=device_id,
                client_upload_id=(
                    metadata.client_upload_id
                ),
                capture_session_id=(
                    metadata.capture_session_id
                ),
                snippet_sequence=(
                    metadata.snippet_sequence
                ),
                original_filename=(
                    finalized_file.original_filename
                ),
                stored_filename=(
                    finalized_file.stored_filename
                ),
                file_path=str(
                    finalized_file.file_path
                ),
                checksum_sha256=(
                    finalized_file.checksum_sha256
                ),
                file_size_bytes=(
                    finalized_file.file_size_bytes
                ),
                capture_started_at=(
                    metadata.capture_started_at
                ),
                recorded_at=recorded_at,
                roi_start_seconds=(
                    metadata.roi_start_seconds
                ),
                roi_end_seconds=(
                    metadata.roi_end_seconds
                ),
                duration_seconds=(
                    finalized_file.duration_seconds
                ),
                sample_rate=(
                    finalized_file.sample_rate
                ),
                channel_count=(
                    finalized_file.channel_count
                ),
                latitude=metadata.latitude,
                longitude=metadata.longitude,
                edge_processing_version=(
                    metadata.edge_processing_version
                ),
                edge_processing_metadata=dict(
                    metadata.edge_processing_metadata
                ),
                processing_status=ProcessingStatus.PENDING,
                processing_error=None,
            )

            await self.recording_repository.create(
                recording
            )

            await self.session.commit()
            await self.session.refresh(recording)

            return RecordingUploadResult(
                recording=recording,
                created=True,
            )

        except IntegrityError as exception:
            await self.session.rollback()

            await self._clean_up_upload_files(
                staged_file=staged_file,
                finalized_file=finalized_file,
            )

            existing_upload = (
                await self.recording_repository
                .get_by_client_upload_id(
                    device_id=device_id,
                    client_upload_id=(
                        metadata.client_upload_id
                    ),
                )
            )

            if (
                existing_upload is not None
                and staged_file is not None
                and existing_upload.checksum_sha256
                == staged_file.checksum_sha256
            ):
                return RecordingUploadResult(
                    recording=existing_upload,
                    created=False,
                )

            raise ResourceConflictError(
                "The ROI snippet conflicts with an existing "
                "recording."
            ) from exception

        except Exception:
            await self.session.rollback()

            await self._clean_up_upload_files(
                staged_file=staged_file,
                finalized_file=finalized_file,
            )

            raise

    def _validate_roi_duration(
        self,
        *,
        metadata: RecordingUploadMetadata,
        staged_file: StoredAudioFile,
    ) -> None:
        metadata_duration = (
            metadata.roi_duration_seconds
        )

        audio_duration = (
            staged_file.duration_seconds
        )

        duration_difference = abs(
            metadata_duration - audio_duration
        )

        if (
            duration_difference
            > settings.roi_duration_tolerance_seconds
        ):
            raise InvalidUploadMetadataError(
                "The ROI interval does not match the uploaded "
                "audio duration. "
                f"Metadata duration: {metadata_duration:.3f}s. "
                f"WAV duration: {audio_duration:.3f}s. "
                "Maximum allowed difference: "
                f"{settings.roi_duration_tolerance_seconds:.3f}s."
            )

    async def _clean_up_upload_files(
        self,
        *,
        staged_file: StoredAudioFile | None,
        finalized_file: StoredAudioFile | None,
    ) -> None:
        if finalized_file is not None:
            await self.storage_service.delete_file(
                finalized_file.file_path
            )
            return

        if staged_file is not None:
            await self.storage_service.delete_file(
                staged_file.file_path
            )

    async def get_recording(
        self,
        recording_id: uuid.UUID,
    ) -> Recording:
        recording = (
            await self.recording_repository.get_by_id(
                recording_id
            )
        )

        if recording is None:
            raise ResourceNotFoundError(
                f"Recording '{recording_id}' was not found."
            )

        return recording

    async def list_recordings(
        self,
        *,
        page: int,
        page_size: int,
        device_id: uuid.UUID | None = None,
        capture_session_id: uuid.UUID | None = None,
        processing_status: ProcessingStatus | None = None,
    ) -> PaginatedResponse[RecordingSummaryResponse]:
        offset = (page - 1) * page_size

        recordings = await self.recording_repository.list(
            offset=offset,
            limit=page_size,
            device_id=device_id,
            capture_session_id=capture_session_id,
            processing_status=processing_status,
        )

        total_items = await self.recording_repository.count(
            device_id=device_id,
            capture_session_id=capture_session_id,
            processing_status=processing_status,
        )

        total_pages = (
            math.ceil(total_items / page_size)
            if total_items > 0
            else 0
        )

        return PaginatedResponse[
            RecordingSummaryResponse
        ](
            items=[
                RecordingSummaryResponse.model_validate(
                    recording
                )
                for recording in recordings
            ],
            pagination=PaginationMetadata(
                page=page,
                page_size=page_size,
                total_items=total_items,
                total_pages=total_pages,
            ),
        )

    async def delete_recording(
        self,
        recording_id: uuid.UUID,
    ) -> None:
        recording = await self.get_recording(
            recording_id
        )

        file_path = Path(recording.file_path)

        await self.recording_repository.delete(
            recording
        )

        await self.session.commit()

        await self.storage_service.delete_file(
            file_path
        )