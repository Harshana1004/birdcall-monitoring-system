from __future__ import annotations

import asyncio
import hashlib
import shutil
import uuid
from dataclasses import dataclass
from datetime import (
    datetime,
    timedelta,
    timezone,
)
from pathlib import Path

import soundfile as sf
from sqlalchemy import (
    select,
)
from sqlalchemy.ext.asyncio import (
    AsyncSession,
)

from src.core.config import (
    settings,
)
from src.core.exceptions import (
    InvalidAudioFileError,
)
from src.models import (
    Detection,
    Device,
    ProcessingStatus,
    Recording,
)
from src.services.audio_processing import (
    AudioProcessingResult,
    AudioProcessingService,
    ProcessedROI,
)
from src.services.birdnet import (
    BirdNetService,
)


MANUAL_PROCESSING_VERSION = (
    "backend-analysis-1.0.0"
)


# ============================================================
# Reserved manual-upload device
# ============================================================


async def get_or_create_manual_device(
    session: AsyncSession,
) -> Device:
    """
    Return the reserved virtual device used for manual audio
    analysis.
    """

    statement = (
        select(
            Device
        )
        .where(
            Device.device_code
            == settings
            .manual_upload_device_code
        )
    )

    result = await session.execute(
        statement
    )

    device = (
        result.scalar_one_or_none()
    )

    if device is not None:
        return device

    device = Device(
        device_code=(
            settings
            .manual_upload_device_code
        ),

        name=(
            settings
            .manual_upload_device_name
        ),

        description=(
            "Reserved virtual device for audio "
            "files uploaded manually through the "
            "analysis API."
        ),

        is_active=True,
    )

    session.add(
        device
    )

    await session.commit()

    await session.refresh(
        device
    )

    return device


# ============================================================
# Result objects
# ============================================================


@dataclass(
    frozen=True
)
class ManualAnalysisRecordingResult:
    """
    One persisted ROI and its BirdNET detections.
    """

    recording: Recording

    detections: list[
        Detection
    ]


@dataclass(
    frozen=True
)
class ManualAnalysisResult:
    """
    Complete result of processing one manually uploaded
    source recording.
    """

    capture_session_id: (
        uuid.UUID
    )

    original_filename: str

    original_file_path: Path

    capture_started_at: (
        datetime
    )

    processing_result: (
        AudioProcessingResult
    )

    recordings: list[
        ManualAnalysisRecordingResult
    ]


# ============================================================
# Manual-analysis service
# ============================================================


class ManualAnalysisService:
    """
    Permanent manual audio-analysis workflow.

    Pipeline:

        source WAV
            ↓
        backend audio preprocessing
            ↓
        all ROIs persisted
            ↓
        ONE batched BirdNET inference call
            ↓
        detections persisted
            ↓
        completed analysis response

    The generated ROI snippets reuse the existing Recording
    and Detection database models under MANUAL-UPLOAD.
    """

    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        self.session = (
            session
        )

        self.audio_processing = (
            AudioProcessingService()
        )

        self.birdnet_service = (
            BirdNetService()
        )

    # ========================================================
    # Main workflow
    # ========================================================

    async def analyze_file(
        self,
        *,
        source_file_path: (
            str | Path
        ),
        original_filename: str,
    ) -> ManualAnalysisResult:
        """
        Analyze one complete manually uploaded source file.
        """

        source_path = (
            Path(
                source_file_path
            )
        )

        if not source_path.exists():
            raise InvalidAudioFileError(
                "The uploaded source audio "
                "file does not exist: "
                f"'{source_path}'."
            )

        if not source_path.is_file():
            raise InvalidAudioFileError(
                "The uploaded source audio "
                "path does not reference a file."
            )

        # ----------------------------------------------------
        # Reserved virtual device
        # ----------------------------------------------------

        manual_device = (
            await get_or_create_manual_device(
                self.session
            )
        )

        # ----------------------------------------------------
        # One uploaded source = one capture session
        # ----------------------------------------------------

        capture_session_id = (
            uuid.uuid4()
        )

        capture_started_at = (
            datetime.now(
                timezone.utc
            )
        )

        # ----------------------------------------------------
        # Preserve original source WAV
        # ----------------------------------------------------

        analysis_directory = (
            settings
            .analysis_storage_directory
            .resolve()
            / str(
                capture_session_id
            )
        )

        analysis_directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        original_path = (
            analysis_directory
            / "original.wav"
        )

        try:
            await asyncio.to_thread(
                shutil.copy2,
                source_path,
                original_path,
            )

            # ------------------------------------------------
            # Process complete source audio once
            # ------------------------------------------------

            processing_result = (
                await asyncio.to_thread(
                    self.audio_processing
                    .process,
                    original_path,
                )
            )

            # ------------------------------------------------
            # Persist every extracted ROI BEFORE BirdNET
            # ------------------------------------------------

            stored_recordings: list[
                Recording
            ] = []

            for roi in (
                processing_result.rois
            ):
                recording = (
                    await self._persist_roi(
                        manual_device=(
                            manual_device
                        ),

                        capture_session_id=(
                            capture_session_id
                        ),

                        capture_started_at=(
                            capture_started_at
                        ),

                        processing_result=(
                            processing_result
                        ),

                        roi=(
                            roi
                        ),

                        original_filename=(
                            original_filename
                        ),
                    )
                )

                stored_recordings.append(
                    recording
                )

            # ------------------------------------------------
            # One BirdNET batch for every extracted ROI
            # ------------------------------------------------

            recording_results = (
                await self
                ._process_recordings_batch(
                    stored_recordings
                )
            )

            return ManualAnalysisResult(
                capture_session_id=(
                    capture_session_id
                ),

                original_filename=(
                    original_filename
                ),

                original_file_path=(
                    original_path
                ),

                capture_started_at=(
                    capture_started_at
                ),

                processing_result=(
                    processing_result
                ),

                recordings=(
                    recording_results
                ),
            )

        except Exception:
            await self.session.rollback()

            raise

    # ========================================================
    # Persist one ROI
    # ========================================================

    async def _persist_roi(
        self,
        *,
        manual_device: Device,
        capture_session_id: (
            uuid.UUID
        ),
        capture_started_at: (
            datetime
        ),
        processing_result: (
            AudioProcessingResult
        ),
        roi: ProcessedROI,
        original_filename: str,
    ) -> Recording:
        """
        Persist one processed ROI as an ordinary Recording.

        BirdNET is deliberately NOT called here. All ROIs are
        persisted first and then classified together.
        """

        recording_id = (
            uuid.uuid4()
        )

        # ----------------------------------------------------
        # Recording storage
        # ----------------------------------------------------

        device_directory = (
            settings
            .audio_storage_directory
            .resolve()
            / str(
                manual_device.id
            )
        )

        device_directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        stored_filename = (
            f"{recording_id}.wav"
        )

        stored_path = (
            device_directory
            / stored_filename
        )

        # ----------------------------------------------------
        # Write processed BirdNET-ready ROI
        # ----------------------------------------------------

        await asyncio.to_thread(
            self._write_roi_wav,
            roi.audio,
            processing_result
            .sample_rate,
            stored_path,
        )

        # ----------------------------------------------------
        # Stored-file metadata
        # ----------------------------------------------------

        checksum_sha256 = (
            await asyncio.to_thread(
                self._calculate_sha256,
                stored_path,
            )
        )

        file_size_bytes = (
            stored_path
            .stat()
            .st_size
        )

        duration_seconds = (
            len(
                roi.audio
            )
            / processing_result
            .sample_rate
        )

        recorded_at = (
            capture_started_at
            + timedelta(
                seconds=(
                    roi.region
                    .start_time
                )
            )
        )

        # ----------------------------------------------------
        # ORM object
        # ----------------------------------------------------

        recording = Recording(
            id=(
                recording_id
            ),

            device_id=(
                manual_device.id
            ),

            client_upload_id=None,

            capture_session_id=(
                capture_session_id
            ),

            snippet_sequence=(
                roi.index
            ),

            original_filename=(
                original_filename
            ),

            stored_filename=(
                stored_filename
            ),

            file_path=str(
                stored_path
            ),

            checksum_sha256=(
                checksum_sha256
            ),

            file_size_bytes=(
                file_size_bytes
            ),

            capture_started_at=(
                capture_started_at
            ),

            recorded_at=(
                recorded_at
            ),

            roi_start_seconds=(
                roi.region
                .start_time
            ),

            roi_end_seconds=(
                roi.region
                .end_time
            ),

            duration_seconds=float(
                duration_seconds
            ),

            sample_rate=(
                processing_result
                .sample_rate
            ),

            channel_count=1,

            latitude=None,

            longitude=None,

            edge_processing_version=(
                MANUAL_PROCESSING_VERSION
            ),

            edge_processing_metadata={
                "source": (
                    "manual_upload"
                ),

                "processing_location": (
                    "backend"
                ),

                "original_filename": (
                    original_filename
                ),

                "original_audio": {
                    "duration_seconds": (
                        processing_result
                        .duration_seconds
                    ),

                    "sample_rate": (
                        processing_result
                        .sample_rate
                    ),
                },

                "normalization": {
                    "enabled": True,

                    "method": (
                        "peak_normalization"
                    ),
                },

                "roi_detection": {
                    "method": (
                        "short_time_energy"
                    ),

                    "frame_duration_seconds": (
                        self
                        .audio_processing
                        .frame_duration
                    ),

                    "hop_duration_seconds": (
                        self
                        .audio_processing
                        .hop_duration
                    ),

                    "threshold_method": (
                        "median_energy_factor"
                    ),

                    "threshold_factor": (
                        self
                        .audio_processing
                        .roi_threshold_factor
                    ),

                    "energy_threshold": (
                        processing_result
                        .energy_threshold
                    ),

                    "minimum_duration_seconds": (
                        self
                        .audio_processing
                        .roi_min_duration
                    ),

                    "merge_gap_seconds": (
                        self
                        .audio_processing
                        .roi_merge_gap
                    ),

                    "boundary_padding_seconds": (
                        self
                        .audio_processing
                        .roi_padding
                    ),
                },

                "roi": {
                    "index": (
                        roi.index
                    ),

                    "start_time_seconds": (
                        roi.region
                        .start_time
                    ),

                    "end_time_seconds": (
                        roi.region
                        .end_time
                    ),

                    "original_duration_seconds": (
                        roi
                        .original_duration_seconds
                    ),

                    "stored_duration_seconds": (
                        duration_seconds
                    ),
                },

                "birdnet_padding": {
                    "minimum_duration_seconds": (
                        self
                        .audio_processing
                        .birdnet_min_duration
                    ),

                    "applied": (
                        roi
                        .original_duration_seconds
                        < self
                        .audio_processing
                        .birdnet_min_duration
                    ),
                },

                "high_pass_filter": {
                    "enabled": True,

                    "type": (
                        "butterworth"
                    ),

                    "cutoff_hz": (
                        self
                        .audio_processing
                        .highpass_cutoff
                    ),

                    "order": (
                        self
                        .audio_processing
                        .highpass_filter_order
                    ),
                },

                "birdnet_batch_processing": {
                    "enabled": True,

                    "batch_size": (
                        settings
                        .birdnet_batch_size
                    ),

                    "workers": (
                        settings
                        .birdnet_workers
                    ),

                    "producers": (
                        settings
                        .birdnet_producers
                    ),
                },
            },

            processing_status=(
                ProcessingStatus.PENDING
            ),

            processing_error=None,
        )

        try:
            self.session.add(
                recording
            )

            await self.session.commit()

            await self.session.refresh(
                recording
            )

            return (
                recording
            )

        except Exception:
            await self.session.rollback()

            await asyncio.to_thread(
                stored_path.unlink,
                missing_ok=True,
            )

            raise

    # ========================================================
    # Batched BirdNET processing
    # ========================================================

    async def _process_recordings_batch(
        self,
        recordings: list[
            Recording
        ],
    ) -> list[
        ManualAnalysisRecordingResult
    ]:
        """
        Run every ROI from one source recording through one
        BirdNET batch operation.
        """

        if not recordings:
            return []

        recording_ids = [
            recording.id
            for recording
            in recordings
        ]

        # ----------------------------------------------------
        # Mark all ROI recordings PROCESSING
        # ----------------------------------------------------

        processing_started_at = (
            datetime.now(
                timezone.utc
            )
        )

        for recording in (
            recordings
        ):
            recording.processing_status = (
                ProcessingStatus.PROCESSING
            )

            recording.processing_started_at = (
                processing_started_at
            )

            recording.processed_at = None

            recording.processing_error = (
                None
            )

        await self.session.commit()

        # ----------------------------------------------------
        # Map stored WAV paths back to Recording objects
        # ----------------------------------------------------

        audio_paths: list[
            Path
        ] = []

        path_to_recording: dict[
            Path,
            Recording,
        ] = {}

        for recording in (
            recordings
        ):
            audio_path = (
                Path(
                    recording.file_path
                ).resolve()
            )

            audio_paths.append(
                audio_path
            )

            path_to_recording[
                audio_path
            ] = (
                recording
            )

        try:
            # ------------------------------------------------
            # ONE BirdNET CALL
            # ------------------------------------------------

            predictions_by_path = (
                await self
                .birdnet_service
                .analyze_batch(
                    audio_paths
                )
            )

            completed_at = (
                datetime.now(
                    timezone.utc
                )
            )

            results: list[
                ManualAnalysisRecordingResult
            ] = []

            # ------------------------------------------------
            # Convert predictions into Detection rows
            # ------------------------------------------------

            for audio_path in (
                audio_paths
            ):
                recording = (
                    path_to_recording[
                        audio_path
                    ]
                )

                predictions = (
                    predictions_by_path
                    .get(
                        audio_path,
                        [],
                    )
                )

                detections: list[
                    Detection
                ] = []

                for prediction in (
                    predictions
                ):
                    detection = (
                        Detection(
                            recording_id=(
                                recording.id
                            ),

                            scientific_name=(
                                prediction
                                .scientific_name
                            ),

                            common_name=(
                                prediction
                                .common_name
                            ),

                            confidence=(
                                prediction
                                .confidence
                            ),

                            start_time_seconds=(
                                prediction
                                .start_time_seconds
                            ),

                            end_time_seconds=(
                                prediction
                                .end_time_seconds
                            ),

                            model_name=(
                                settings
                                .birdnet_model_name
                            ),

                            model_version=(
                                settings
                                .birdnet_model_version
                            ),
                        )
                    )

                    self.session.add(
                        detection
                    )

                    detections.append(
                        detection
                    )

                recording.processing_status = (
                    ProcessingStatus.COMPLETED
                )

                recording.processed_at = (
                    completed_at
                )

                recording.processing_error = (
                    None
                )

                results.append(
                    ManualAnalysisRecordingResult(
                        recording=(
                            recording
                        ),

                        detections=(
                            detections
                        ),
                    )
                )

            # ------------------------------------------------
            # One commit for all BirdNET results
            # ------------------------------------------------

            await self.session.commit()

            # ------------------------------------------------
            # Refresh generated values
            # ------------------------------------------------

            for result in (
                results
            ):
                await self.session.refresh(
                    result.recording
                )

                for detection in (
                    result.detections
                ):
                    await self.session.refresh(
                        detection
                    )

            return (
                results
            )

        except Exception as exception:
            await self.session.rollback()

            failed_at = (
                datetime.now(
                    timezone.utc
                )
            )

            error_message = str(
                exception
            ).strip()

            if not error_message:
                error_message = (
                    exception
                    .__class__
                    .__name__
                )

            # ------------------------------------------------
            # Mark every ROI from the failed batch FAILED
            # ------------------------------------------------

            for recording_id in (
                recording_ids
            ):
                recording = (
                    await self.session.get(
                        Recording,
                        recording_id,
                    )
                )

                if recording is None:
                    continue

                recording.processing_status = (
                    ProcessingStatus.FAILED
                )

                recording.processed_at = (
                    failed_at
                )

                recording.processing_error = (
                    error_message[
                        :1000
                    ]
                )

            await self.session.commit()

            raise

    # ========================================================
    # Retrieve previous session recordings
    # ========================================================

    async def get_session_recordings(
        self,
        capture_session_id: (
            uuid.UUID
        ),
    ) -> list[
        Recording
    ]:
        manual_device = (
            await get_or_create_manual_device(
                self.session
            )
        )

        statement = (
            select(
                Recording
            )
            .where(
                Recording.device_id
                == manual_device.id,

                Recording.capture_session_id
                == capture_session_id,
            )
            .order_by(
                Recording
                .snippet_sequence
                .asc()
            )
        )

        result = await self.session.execute(
            statement
        )

        return list(
            result
            .scalars()
            .all()
        )

    # ========================================================
    # Retrieve previous session detections
    # ========================================================

    async def get_session_detections(
        self,
        capture_session_id: (
            uuid.UUID
        ),
    ) -> list[
        Detection
    ]:
        manual_device = (
            await get_or_create_manual_device(
                self.session
            )
        )

        statement = (
            select(
                Detection
            )
            .join(
                Recording,
                Detection.recording_id
                == Recording.id,
            )
            .where(
                Recording.device_id
                == manual_device.id,

                Recording.capture_session_id
                == capture_session_id,
            )
            .order_by(
                Recording
                .snippet_sequence
                .asc(),

                Detection
                .confidence
                .desc(),
            )
        )

        result = await self.session.execute(
            statement
        )

        return list(
            result
            .scalars()
            .all()
        )

    # ========================================================
    # Original source path
    # ========================================================

    @staticmethod
    def get_original_audio_path(
        capture_session_id: (
            uuid.UUID
        ),
    ) -> Path:
        return (
            settings
            .analysis_storage_directory
            .resolve()
            / str(
                capture_session_id
            )
            / "original.wav"
        )

    # ========================================================
    # File helpers
    # ========================================================

    @staticmethod
    def _write_roi_wav(
        audio,
        sample_rate: int,
        file_path: Path,
    ) -> None:
        sf.write(
            file_path,
            audio,
            sample_rate,
            subtype="PCM_16",
        )

    @staticmethod
    def _calculate_sha256(
        file_path: Path,
    ) -> str:
        checksum = (
            hashlib.sha256()
        )

        with file_path.open(
            "rb"
        ) as audio_file:
            while True:
                chunk = (
                    audio_file.read(
                        1024
                        * 1024
                    )
                )

                if not chunk:
                    break

                checksum.update(
                    chunk
                )

        return (
            checksum.hexdigest()
        )