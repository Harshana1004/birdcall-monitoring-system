import logging
import math
import uuid
from dataclasses import dataclass
from datetime import (
    datetime,
    timedelta,
    timezone,
)
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy import (
    func,
    select,
)
from sqlalchemy.exc import (
    IntegrityError,
)
from sqlalchemy.ext.asyncio import (
    AsyncSession,
)

from src.api.schemas import (
    PaginatedResponse,
    PaginationMetadata,
    RecordingSummaryResponse,
    RecordingUploadMetadata,
)
from src.core.config import settings
from src.core.exceptions import (
    DeviceNotFoundError,
    InactiveDeviceError,
    InvalidUploadMetadataError,
    ProcessingError,
    RecordingConflictError,
    RecordingNotFoundError,
)
from src.models import (
    Detection,
    Device,
    ProcessingStatus,
    Recording,
)
from src.services.audio import (
    AudioStorage,
    StoredAudioFile,
)
from src.services.birdnet import (
    BirdNetPrediction,
    BirdNetService,
)


logger = logging.getLogger(
    __name__
)


# ============================================================
# Upload result
# ============================================================


@dataclass(
    frozen=True
)
class RecordingUploadResult:
    """
    Result of either a new recording upload or an idempotent
    retry.
    """

    recording: Recording
    created: bool


# ============================================================
# Recording service
# ============================================================


class RecordingService:
    """
    Handle recording uploads, retrieval, deletion and BirdNET
    processing.

    Recording operations remain inside a service because they
    coordinate both PostgreSQL and filesystem state and also
    trigger the BirdNET classification pipeline.
    """

    def __init__(
        self,
        session: AsyncSession,
        birdnet_service: BirdNetService | None = None,
    ) -> None:
        self.session = session

        self.audio_storage = (
            AudioStorage()
        )

        self.birdnet_service = (
            birdnet_service
            if birdnet_service is not None
            else BirdNetService()
        )

    # ========================================================
    # Upload recording
    # ========================================================

    async def upload_recording(
        self,
        *,
        device_id: uuid.UUID,
        upload: UploadFile,
        metadata: RecordingUploadMetadata,
    ) -> RecordingUploadResult:
        """
        Validate and persist one edge-generated ROI snippet.

        Two separate duplicate protections are used:

        1. client_upload_id
           Allows the ESP32 to safely retry a network upload.

        2. SHA-256 checksum
           Prevents identical audio content being stored more
           than once for the same device.
        """

        # ----------------------------------------------------
        # Verify device
        # ----------------------------------------------------

        device = await self.session.get(
            Device,
            device_id,
        )

        if device is None:
            raise DeviceNotFoundError(
                f"Device '{device_id}' was not found."
            )

        if not device.is_active:
            raise InactiveDeviceError()

        staged_file: (
            StoredAudioFile | None
        ) = None

        finalized_file: (
            StoredAudioFile | None
        ) = None

        try:
            # ------------------------------------------------
            # Stage and validate WAV file
            # ------------------------------------------------

            staged_file = (
                await self.audio_storage.stage_upload(
                    upload
                )
            )

            # ------------------------------------------------
            # Check idempotent retry
            # ------------------------------------------------

            existing_upload = (
                await self._get_by_client_upload_id(
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
                    raise RecordingConflictError(
                        "The client_upload_id has already "
                        "been used for a different audio file."
                    )

                await self.audio_storage.delete_file(
                    staged_file.file_path
                )

                return RecordingUploadResult(
                    recording=existing_upload,
                    created=False,
                )

            # ------------------------------------------------
            # Duplicate-content protection
            # ------------------------------------------------

            duplicate_content = (
                await self._get_by_checksum(
                    device_id=device_id,
                    checksum_sha256=(
                        staged_file.checksum_sha256
                    ),
                )
            )

            if duplicate_content is not None:
                raise RecordingConflictError(
                    "An identical audio snippet has already "
                    "been uploaded for this device. "
                    "Existing recording ID: "
                    f"{duplicate_content.id}."
                )

            # ------------------------------------------------
            # Validate metadata duration against WAV duration
            # ------------------------------------------------

            self._validate_roi_duration(
                metadata=metadata,
                staged_file=staged_file,
            )

            # ------------------------------------------------
            # Assign recording ID
            # ------------------------------------------------

            recording_id = (
                uuid.uuid4()
            )

            # ------------------------------------------------
            # Move WAV to permanent storage
            # ------------------------------------------------

            finalized_file = (
                await self.audio_storage.finalize_upload(
                    staged_file,
                    device_id=device_id,
                    recording_id=recording_id,
                )
            )

            # ------------------------------------------------
            # Calculate actual ROI timestamp
            # ------------------------------------------------

            recorded_at = (
                metadata.capture_started_at
                + timedelta(
                    seconds=(
                        metadata.roi_start_seconds
                    ),
                )
            )

            # ------------------------------------------------
            # Create Recording database entity
            # ------------------------------------------------

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

                recorded_at=(
                    recorded_at
                ),

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

                latitude=(
                    metadata.latitude
                ),

                longitude=(
                    metadata.longitude
                ),

                edge_processing_version=(
                    metadata.edge_processing_version
                ),

                edge_processing_metadata=dict(
                    metadata.edge_processing_metadata
                ),

                processing_status=(
                    ProcessingStatus.PENDING
                ),

                processing_error=None,
            )

            self.session.add(
                recording
            )

            await self.session.flush()

            await self.session.commit()

            await self.session.refresh(
                recording
            )

            return RecordingUploadResult(
                recording=recording,
                created=True,
            )

        # ----------------------------------------------------
        # Database uniqueness/concurrency conflict
        # ----------------------------------------------------

        except IntegrityError as exception:
            await self.session.rollback()

            await self._clean_up_upload_files(
                staged_file=staged_file,
                finalized_file=finalized_file,
            )

            existing_upload = (
                await self._get_by_client_upload_id(
                    device_id=device_id,
                    client_upload_id=(
                        metadata.client_upload_id
                    ),
                )
            )

            if (
                existing_upload is not None
                and staged_file is not None
                and (
                    existing_upload.checksum_sha256
                    == staged_file.checksum_sha256
                )
            ):
                return RecordingUploadResult(
                    recording=existing_upload,
                    created=False,
                )

            raise RecordingConflictError(
                "The ROI snippet conflicts with an "
                "existing recording."
            ) from exception

        except Exception:
            await self.session.rollback()

            await self._clean_up_upload_files(
                staged_file=staged_file,
                finalized_file=finalized_file,
            )

            raise

    # ========================================================
    # Get recording
    # ========================================================

    async def get_recording(
        self,
        recording_id: uuid.UUID,
    ) -> Recording:
        """
        Return one recording or raise a 404 error.
        """

        recording = await self.session.get(
            Recording,
            recording_id,
        )

        if recording is None:
            raise RecordingNotFoundError(
                f"Recording '{recording_id}' was not found."
            )

        return recording

    # ========================================================
    # List recordings
    # ========================================================

    async def list_recordings(
        self,
        *,
        page: int,
        page_size: int,
        device_id: uuid.UUID | None = None,
        capture_session_id: (
            uuid.UUID | None
        ) = None,
        processing_status: (
            ProcessingStatus | None
        ) = None,
    ) -> PaginatedResponse[
        RecordingSummaryResponse
    ]:
        """
        Return a paginated list of recordings.
        """

        conditions = []

        if device_id is not None:
            conditions.append(
                Recording.device_id
                == device_id
            )

        if capture_session_id is not None:
            conditions.append(
                Recording.capture_session_id
                == capture_session_id
            )

        if processing_status is not None:
            conditions.append(
                Recording.processing_status
                == processing_status
            )

        # ----------------------------------------------------
        # Count matching rows
        # ----------------------------------------------------

        count_statement = select(
            func.count(
                Recording.id
            )
        )

        if conditions:
            count_statement = (
                count_statement.where(
                    *conditions
                )
            )

        total_items = (
            await self.session.scalar(
                count_statement
            )
        ) or 0

        # ----------------------------------------------------
        # Retrieve requested page
        # ----------------------------------------------------

        offset = (
            page - 1
        ) * page_size

        statement = (
            select(Recording)
            .order_by(
                Recording.recorded_at.desc(),
                Recording.snippet_sequence.asc(),
            )
            .offset(offset)
            .limit(page_size)
        )

        if conditions:
            statement = (
                statement.where(
                    *conditions
                )
            )

        result = await self.session.execute(
            statement
        )

        recordings = (
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

    # ========================================================
    # Delete recording
    # ========================================================

    async def delete_recording(
        self,
        recording_id: uuid.UUID,
    ) -> None:
        """
        Delete one recording.

        Associated Detection rows are removed through the
        existing database relationship/cascade configuration.
        """

        recording = (
            await self.get_recording(
                recording_id
            )
        )

        file_path = Path(
            recording.file_path
        )

        await self.session.delete(
            recording
        )

        await self.session.commit()

        # Only delete the WAV after the database transaction
        # succeeds.
        await self.audio_storage.delete_file(
            file_path
        )

    # ========================================================
    # BirdNET processing
    # ========================================================

    async def process_recording(
        self,
        recording_id: uuid.UUID,
    ) -> None:
        """
        Run BirdNET on one uploaded ROI and persist detections.

        Processing lifecycle:

            PENDING
               ↓
            PROCESSING
               ↓
            COMPLETED

        Failure lifecycle:

            PROCESSING
               ↓
            FAILED
        """

        recording = await self.session.get(
            Recording,
            recording_id,
        )

        if recording is None:
            logger.error(
                "Recording %s does not exist and cannot "
                "be processed.",
                recording_id,
            )

            return

        # ----------------------------------------------------
        # Prevent unnecessary duplicate processing
        # ----------------------------------------------------

        if (
            recording.processing_status
            == ProcessingStatus.COMPLETED
        ):
            logger.info(
                "Recording %s has already been processed. "
                "Skipping duplicate processing request.",
                recording_id,
            )

            return

        if (
            recording.processing_status
            == ProcessingStatus.PROCESSING
        ):
            logger.warning(
                "Recording %s is already being processed. "
                "Skipping concurrent processing request.",
                recording_id,
            )

            return

        try:
            # ------------------------------------------------
            # Mark processing
            # ------------------------------------------------

            await self._mark_processing(
                recording
            )

            # ------------------------------------------------
            # Resolve WAV path
            # ------------------------------------------------

            audio_path = (
                self._resolve_audio_path(
                    recording.file_path
                )
            )

            # ------------------------------------------------
            # BirdNET inference
            # ------------------------------------------------

            predictions = (
                await self.birdnet_service.analyze(
                    audio_path
                )
            )

            # ------------------------------------------------
            # Replace detections
            # ------------------------------------------------

            await self._replace_detections(
                recording=recording,
                predictions=predictions,
            )

            # ------------------------------------------------
            # Complete processing
            # ------------------------------------------------

            await self._mark_completed(
                recording
            )

            logger.info(
                "Recording %s processed successfully. "
                "%s detection(s) were stored.",
                recording_id,
                len(predictions),
            )

        except Exception as exception:
            logger.exception(
                "BirdNET processing failed for "
                "recording %s.",
                recording_id,
            )

            await self.session.rollback()

            await self._mark_failed(
                recording_id=recording_id,
                exception=exception,
            )

    # ========================================================
    # Processing-state helpers
    # ========================================================

    async def _mark_processing(
        self,
        recording: Recording,
    ) -> None:
        """
        Persist PROCESSING state before BirdNET inference begins.
        """

        recording.processing_status = (
            ProcessingStatus.PROCESSING
        )

        recording.processing_started_at = (
            datetime.now(
                timezone.utc
            )
        )

        recording.processed_at = None

        recording.processing_error = None

        await self.session.commit()

        await self.session.refresh(
            recording
        )

    async def _mark_completed(
        self,
        recording: Recording,
    ) -> None:
        """
        Persist detections and COMPLETED state atomically.
        """

        recording.processing_status = (
            ProcessingStatus.COMPLETED
        )

        recording.processed_at = (
            datetime.now(
                timezone.utc
            )
        )

        recording.processing_error = None

        await self.session.commit()

        await self.session.refresh(
            recording
        )

    async def _mark_failed(
        self,
        *,
        recording_id: uuid.UUID,
        exception: Exception,
    ) -> None:
        """
        Persist FAILED state after a processing error.
        """

        recording = await self.session.get(
            Recording,
            recording_id,
        )

        if recording is None:
            logger.error(
                "Recording %s could not be marked as failed "
                "because it no longer exists.",
                recording_id,
            )

            return

        recording.processing_status = (
            ProcessingStatus.FAILED
        )

        recording.processed_at = (
            datetime.now(
                timezone.utc
            )
        )

        recording.processing_error = (
            self._safe_error_message(
                exception
            )
        )

        try:
            await self.session.commit()

        except Exception:
            await self.session.rollback()

            logger.exception(
                "Could not persist failed processing state "
                "for recording %s.",
                recording_id,
            )

    # ========================================================
    # Detection replacement
    # ========================================================

    async def _replace_detections(
        self,
        *,
        recording: Recording,
        predictions: list[
            BirdNetPrediction
        ],
    ) -> None:
        """
        Replace existing detections with the newest BirdNET
        predictions.

        This prevents duplicate Detection rows if a recording is
        intentionally reprocessed.
        """

        statement = select(
            Detection
        ).where(
            Detection.recording_id
            == recording.id
        )

        result = await self.session.execute(
            statement
        )

        existing_detections = (
            result.scalars()
            .all()
        )

        for detection in existing_detections:
            await self.session.delete(
                detection
            )

        for prediction in predictions:
            detection = (
                self._prediction_to_detection(
                    recording=recording,
                    prediction=prediction,
                )
            )

            self.session.add(
                detection
            )

    # ========================================================
    # Prediction conversion
    # ========================================================

    @staticmethod
    def _prediction_to_detection(
        *,
        recording: Recording,
        prediction: BirdNetPrediction,
    ) -> Detection:
        """
        Convert a BirdNET prediction into a Detection ORM entity.
        """

        return Detection(
            recording_id=(
                recording.id
            ),

            scientific_name=(
                prediction.scientific_name
            ),

            common_name=(
                prediction.common_name
            ),

            confidence=(
                prediction.confidence
            ),

            start_time_seconds=(
                prediction.start_time_seconds
            ),

            end_time_seconds=(
                prediction.end_time_seconds
            ),

            model_name=(
                settings.birdnet_model_name
            ),

            model_version=(
                settings.birdnet_model_version
            ),
        )

    # ========================================================
    # Internal recording queries
    # ========================================================

    async def _get_by_client_upload_id(
        self,
        *,
        device_id: uuid.UUID,
        client_upload_id: uuid.UUID,
    ) -> Recording | None:
        """
        Retrieve a recording using its retry-safe upload ID.
        """

        statement = select(
            Recording
        ).where(
            Recording.device_id
            == device_id,

            Recording.client_upload_id
            == client_upload_id,
        )

        result = await self.session.execute(
            statement
        )

        return (
            result.scalar_one_or_none()
        )

    async def _get_by_checksum(
        self,
        *,
        device_id: uuid.UUID,
        checksum_sha256: str,
    ) -> Recording | None:
        """
        Retrieve a recording with identical audio content.
        """

        statement = select(
            Recording
        ).where(
            Recording.device_id
            == device_id,

            Recording.checksum_sha256
            == checksum_sha256,
        )

        result = await self.session.execute(
            statement
        )

        return (
            result.scalar_one_or_none()
        )

    # ========================================================
    # ROI validation
    # ========================================================

    @staticmethod
    def _validate_roi_duration(
        *,
        metadata: RecordingUploadMetadata,
        staged_file: StoredAudioFile,
    ) -> None:
        """
        Verify that the uploaded WAV duration matches the ROI
        interval supplied by the edge device.
        """

        metadata_duration = (
            metadata.roi_duration_seconds
        )

        audio_duration = (
            staged_file.duration_seconds
        )

        duration_difference = abs(
            metadata_duration
            - audio_duration
        )

        if (
            duration_difference
            > settings.roi_duration_tolerance_seconds
        ):
            raise InvalidUploadMetadataError(
                "The ROI interval does not match the "
                "uploaded audio duration. "
                f"Metadata duration: "
                f"{metadata_duration:.3f}s. "
                f"WAV duration: "
                f"{audio_duration:.3f}s. "
                "Maximum allowed difference: "
                f"{settings.roi_duration_tolerance_seconds:.3f}s."
            )

    # ========================================================
    # File cleanup
    # ========================================================

    async def _clean_up_upload_files(
        self,
        *,
        staged_file: StoredAudioFile | None,
        finalized_file: StoredAudioFile | None,
    ) -> None:
        """
        Remove staged/permanent files if an upload transaction
        fails.
        """

        if finalized_file is not None:
            await self.audio_storage.delete_file(
                finalized_file.file_path
            )

            return

        if staged_file is not None:
            await self.audio_storage.delete_file(
                staged_file.file_path
            )

    # ========================================================
    # Audio-path validation
    # ========================================================

    @staticmethod
    def _resolve_audio_path(
        stored_file_path: str,
    ) -> Path:
        """
        Resolve and validate the WAV path stored in PostgreSQL.
        """

        audio_path = Path(
            stored_file_path
        )

        if audio_path.is_absolute():
            resolved_path = (
                audio_path.resolve()
            )

        else:
            resolved_path = (
                Path.cwd()
                / audio_path
            ).resolve()

        if not resolved_path.exists():
            raise ProcessingError(
                "The recording audio file does not exist at "
                f"'{resolved_path}'."
            )

        if not resolved_path.is_file():
            raise ProcessingError(
                "The recording audio path does not reference "
                f"a file: '{resolved_path}'."
            )

        return resolved_path

    # ========================================================
    # Error-message safety
    # ========================================================

    @staticmethod
    def _safe_error_message(
        exception: Exception,
    ) -> str:
        """
        Produce a bounded error string safe for database storage.
        """

        message = str(
            exception
        ).strip()

        if not message:
            message = (
                exception
                .__class__
                .__name__
            )

        return message[:1000]


# ============================================================
# Background processing entry point
# ============================================================


async def process_recording_background(
    recording_id: uuid.UUID,
) -> None:
    """
    Process one Recording using a fresh database session.

    This is used directly by FastAPI BackgroundTasks after the
    upload request completes.
    """

    from src.database import (
        AsyncSessionLocal,
    )

    async with AsyncSessionLocal() as session:
        service = RecordingService(
            session
        )

        await service.process_recording(
            recording_id
        )