import logging
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.exceptions import ProcessingError
from models.detection import Detection
from models.recording import (
    ProcessingStatus,
    Recording,
)
from repositories.detection_repository import (
    DetectionRepository,
)
from repositories.recording_repository import (
    RecordingRepository,
)
from services.birdnet_service import (
    BirdNetPrediction,
    BirdNetService,
)


logger = logging.getLogger(__name__)


class RecordingProcessingService:
    """
    Coordinate BirdNET processing for one uploaded ROI snippet.

    Processing lifecycle:

        pending
            ↓
        processing
            ↓
        completed

    If an error occurs:

        processing
            ↓
        failed
    """

    def __init__(
        self,
        session: AsyncSession,
        birdnet_service: BirdNetService | None = None,
    ) -> None:
        self.session = session

        self.recording_repository = (
            RecordingRepository(
                session
            )
        )

        self.detection_repository = (
            DetectionRepository(
                session
            )
        )

        self.birdnet_service = (
            birdnet_service
            if birdnet_service is not None
            else BirdNetService()
        )

    async def process_recording(
        self,
        recording_id: UUID,
    ) -> None:
        """
        Run BirdNET on one recording and persist its detections.

        The database session supplied to this service must belong
        specifically to the background task.
        """

        recording = (
            await self.recording_repository.get_by_id(
                recording_id
            )
        )

        if recording is None:
            logger.error(
                "Recording %s does not exist and cannot "
                "be processed.",
                recording_id,
            )
            return

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
                "Recording %s is already marked as processing. "
                "Skipping concurrent processing request.",
                recording_id,
            )
            return

        try:
            await self._mark_processing(
                recording
            )

            audio_path = self._resolve_audio_path(
                recording.file_path
            )

            predictions = (
                await self.birdnet_service.analyze(
                    audio_path
                )
            )

            await self._replace_detections(
                recording=recording,
                predictions=predictions,
            )

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

    async def _mark_processing(
        self,
        recording: Recording,
    ) -> None:
        """
        Persist the processing state before inference begins.
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

    async def _replace_detections(
        self,
        *,
        recording: Recording,
        predictions: list[BirdNetPrediction],
    ) -> None:
        """
        Replace existing detections with the latest result.

        This prevents duplicate rows if a failed or manually reset
        recording is processed again.
        """

        await self.detection_repository.delete_by_recording_id(
            recording.id
        )

        detections = [
            self._prediction_to_detection(
                recording=recording,
                prediction=prediction,
            )
            for prediction in predictions
        ]

        await self.detection_repository.create_many(
            detections
        )

    async def _mark_completed(
        self,
        recording: Recording,
    ) -> None:
        """
        Store detections and the completed state atomically.
        """

        recording.processing_status = (
            ProcessingStatus.COMPLETED
        )

        recording.processed_at = datetime.now(
            timezone.utc
        )

        recording.processing_error = None

        await self.session.commit()

        await self.session.refresh(
            recording
        )

    async def _mark_failed(
        self,
        *,
        recording_id: UUID,
        exception: Exception,
    ) -> None:
        """
        Store a failed state after rolling back the failed transaction.
        """

        recording = (
            await self.recording_repository.get_by_id(
                recording_id
            )
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

        recording.processed_at = datetime.now(
            timezone.utc
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
                "Could not store the failed processing state "
                "for recording %s.",
                recording_id,
            )

    @staticmethod
    def _prediction_to_detection(
        *,
        recording: Recording,
        prediction: BirdNetPrediction,
    ) -> Detection:
        """
        Convert one service-level BirdNET prediction into a
        Detection database entity.
        """

        return Detection(
            recording_id=recording.id,
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

    @staticmethod
    def _resolve_audio_path(
        stored_file_path: str,
    ) -> Path:
        """
        Resolve and validate the audio path stored in the database.
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

    @staticmethod
    def _safe_error_message(
        exception: Exception,
    ) -> str:
        """
        Produce a bounded database-safe error message.
        """

        message = str(
            exception
        ).strip()

        if not message:
            message = (
                exception.__class__.__name__
            )

        return message[:1000]