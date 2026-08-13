from __future__ import annotations

import asyncio
import math
import uuid
from pathlib import Path
from typing import Annotated

import numpy as np
from fastapi import (
    APIRouter,
    Depends,
    File,
    Query,
    UploadFile,
    status,
)
from sqlalchemy import (
    func,
    select,
)
from sqlalchemy.ext.asyncio import (
    AsyncSession,
)

from src.api.schemas import (
    AnalysisDetectionResponse,
    AnalysisProcessingResponse,
    AnalysisResponse,
    AnalysisROIResponse,
    AnalysisSummaryResponse,
    AnalysisVisualizationResponse,
    AnalysisVisualizationROIResponse,
    ErrorResponse,
    PaginatedResponse,
    PaginationMetadata,
)
from src.core.config import settings
from src.core.exceptions import (
    InvalidAudioFileError,
    RecordingNotFoundError,
)
from src.database import get_db
from src.models import (
    Detection,
    Recording,
)
from src.services.manual_analysis import (
    ManualAnalysisService,
    get_or_create_manual_device,
)


router = APIRouter(
    prefix="/api/v1/analysis",
    tags=[
        "Manual Audio Analysis"
    ],
)


DatabaseSession = Annotated[
    AsyncSession,
    Depends(
        get_db
    ),
]


# ============================================================
# Helpers
# ============================================================


def _validate_upload_filename(
    upload: UploadFile,
) -> str:
    if not upload.filename:
        raise InvalidAudioFileError(
            "The uploaded audio file must have a filename."
        )

    filename = Path(
        upload.filename
    ).name

    extension = (
        Path(
            filename
        )
        .suffix
        .lower()
        .lstrip(".")
    )

    if (
        extension
        not in settings.allowed_audio_extension_set
    ):
        allowed_extensions = ", ".join(
            sorted(
                settings.allowed_audio_extension_set
            )
        )

        raise InvalidAudioFileError(
            "Unsupported audio file extension. "
            f"Allowed extensions: {allowed_extensions}."
        )

    return filename


async def _save_upload_temporarily(
    upload: UploadFile,
) -> Path:
    """
    Stream a manual upload into temporary analysis storage.

    The ManualAnalysisService later copies it into the permanent
    capture-session directory.
    """

    filename = (
        _validate_upload_filename(
            upload
        )
    )

    temporary_directory = (
        settings
        .analysis_storage_directory
        .resolve()
        / ".temporary"
    )

    temporary_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary_path = (
        temporary_directory
        / f"{uuid.uuid4().hex}_{filename}"
    )

    total_size = 0

    try:
        with temporary_path.open(
            "wb"
        ) as output_file:
            while True:
                chunk = await upload.read(
                    1024 * 1024
                )

                if not chunk:
                    break

                total_size += len(
                    chunk
                )

                if (
                    total_size
                    > settings.max_upload_size_bytes
                ):
                    raise InvalidAudioFileError(
                        "The uploaded file exceeds the "
                        f"{settings.max_upload_size_mb} MB "
                        "size limit."
                    )

                output_file.write(
                    chunk
                )

        if total_size == 0:
            raise InvalidAudioFileError(
                "The uploaded audio file is empty."
            )

        return temporary_path

    except Exception:
        temporary_path.unlink(
            missing_ok=True
        )

        raise

    finally:
        await upload.close()


def _build_roi_response(
    recording: Recording,
    detections: list[
        Detection
    ],
) -> AnalysisROIResponse:
    original_duration = (
        float(
            recording.roi_end_seconds
            - recording.roi_start_seconds
        )
        if (
            recording.roi_start_seconds
            is not None
            and recording.roi_end_seconds
            is not None
        )
        else recording.duration_seconds
    )

    return AnalysisROIResponse(
        recording_id=(
            recording.id
        ),

        snippet_sequence=(
            recording.snippet_sequence
            if recording.snippet_sequence
            is not None
            else 0
        ),

        roi_start_seconds=float(
            recording.roi_start_seconds
            or 0.0
        ),

        roi_end_seconds=float(
            recording.roi_end_seconds
            or recording.duration_seconds
        ),

        original_duration_seconds=(
            original_duration
        ),

        stored_duration_seconds=float(
            recording.duration_seconds
        ),

        processing_status=(
            recording.processing_status
        ),

        detections=[
            AnalysisDetectionResponse.model_validate(
                detection
            )
            for detection
            in detections
        ],
    )


async def _load_detections_for_recordings(
    session: AsyncSession,
    recordings: list[
        Recording
    ],
) -> dict[
    uuid.UUID,
    list[
        Detection
    ],
]:
    if not recordings:
        return {}

    recording_ids = [
        recording.id
        for recording
        in recordings
    ]

    result = await session.execute(
        select(
            Detection
        )
        .where(
            Detection.recording_id.in_(
                recording_ids
            )
        )
        .order_by(
            Detection.recording_id,
            Detection.confidence.desc(),
        )
    )

    mapping: dict[
        uuid.UUID,
        list[
            Detection
        ],
    ] = {
        recording_id: []
        for recording_id
        in recording_ids
    }

    for detection in (
        result.scalars().all()
    ):
        mapping[
            detection.recording_id
        ].append(
            detection
        )

    return mapping


# ============================================================
# Create manual analysis
# ============================================================


@router.post(
    "",
    response_model=AnalysisResponse,
    status_code=(
        status.HTTP_201_CREATED
    ),
    responses={
        413: {
            "model": ErrorResponse,
        },
        422: {
            "model": ErrorResponse,
        },
    },
)
async def analyze_audio(
    audio_file: Annotated[
        UploadFile,
        File(
            description=(
                "Complete WAV recording to process "
                "through the backend audio-analysis pipeline."
            ),
        ),
    ],
    session: DatabaseSession,
) -> AnalysisResponse:
    """
    Upload and permanently analyse one complete WAV recording.

    The backend performs the preprocessing that is normally
    intended for the ESP32, then stores each detected ROI using
    the existing Recording model under MANUAL-UPLOAD.

    BirdNET detections are persisted in the existing Detection
    table.
    """

    original_filename = (
        _validate_upload_filename(
            audio_file
        )
    )

    temporary_path = (
        await _save_upload_temporarily(
            audio_file
        )
    )

    try:
        service = (
            ManualAnalysisService(
                session
            )
        )

        result = (
            await service.analyze_file(
                source_file_path=(
                    temporary_path
                ),
                original_filename=(
                    original_filename
                ),
            )
        )

        roi_responses = [
            AnalysisROIResponse(
                recording_id=(
                    item.recording.id
                ),

                snippet_sequence=(
                    item.recording.snippet_sequence
                    if (
                        item.recording.snippet_sequence
                        is not None
                    )
                    else 0
                ),

                roi_start_seconds=float(
                    item.recording.roi_start_seconds
                    or 0.0
                ),

                roi_end_seconds=float(
                    item.recording.roi_end_seconds
                    or 0.0
                ),

                original_duration_seconds=float(
                    item.recording.roi_end_seconds
                    - item.recording.roi_start_seconds
                ),

                stored_duration_seconds=float(
                    item.recording.duration_seconds
                ),

                processing_status=(
                    item.recording.processing_status
                ),

                detections=[
                    AnalysisDetectionResponse.model_validate(
                        detection
                    )
                    for detection
                    in item.detections
                ],
            )

            for item
            in result.recordings
        ]

        detection_count = sum(
            len(
                item.detections
            )
            for item
            in result.recordings
        )

        return AnalysisResponse(
            capture_session_id=(
                result.capture_session_id
            ),

            original_filename=(
                result.original_filename
            ),

            capture_started_at=(
                result.capture_started_at
            ),

            processing=(
                AnalysisProcessingResponse(
                    sample_rate=(
                        result
                        .processing_result
                        .sample_rate
                    ),

                    duration_seconds=(
                        result
                        .processing_result
                        .duration_seconds
                    ),

                    energy_threshold=(
                        result
                        .processing_result
                        .energy_threshold
                    ),

                    roi_count=len(
                        result.recordings
                    ),

                    detection_count=(
                        detection_count
                    ),

                    normalization_applied=True,

                    high_pass_cutoff_hz=(
                        service
                        .audio_processing
                        .highpass_cutoff
                    ),
                )
            ),

            rois=(
                visualization_rois
            ),
        )

    finally:
        temporary_path.unlink(
            missing_ok=True
        )


# ============================================================
# Retrieve previous analysis
# ============================================================


@router.get(
    "/{capture_session_id}",
    response_model=AnalysisResponse,
)
async def get_analysis(
    capture_session_id: uuid.UUID,
    session: DatabaseSession,
) -> AnalysisResponse:
    """
    Retrieve one previously completed manual-analysis session.
    """

    service = (
        ManualAnalysisService(
            session
        )
    )

    recordings = (
        await service.get_session_recordings(
            capture_session_id
        )
    )

    if not recordings:
        raise RecordingNotFoundError(
            "Manual analysis session "
            f"'{capture_session_id}' was not found."
        )

    detection_mapping = (
        await _load_detections_for_recordings(
            session,
            recordings,
        )
    )

    original_path = (
        service.get_original_audio_path(
            capture_session_id
        )
    )

    if not original_path.exists():
        raise InvalidAudioFileError(
            "The original audio file for this analysis "
            "session is missing."
        )

    processing_result = (
        await asyncio.to_thread(
            service.audio_processing.process,
            original_path,
        )
    )

    first_recording = (
        recordings[0]
    )

    roi_responses = [
        _build_roi_response(
            recording,
            detection_mapping.get(
                recording.id,
                [],
            ),
        )
        for recording
        in recordings
    ]

    detection_count = sum(
        len(
            detection_mapping.get(
                recording.id,
                [],
            )
        )
        for recording
        in recordings
    )

    return AnalysisResponse(
        capture_session_id=(
            capture_session_id
        ),

        original_filename=(
            first_recording.original_filename
        ),

        capture_started_at=(
            first_recording.capture_started_at
            or first_recording.recorded_at
        ),

        processing=(
            AnalysisProcessingResponse(
                sample_rate=(
                    processing_result.sample_rate
                ),

                duration_seconds=(
                    processing_result.duration_seconds
                ),

                energy_threshold=(
                    processing_result.energy_threshold
                ),

                roi_count=len(
                    recordings
                ),

                detection_count=(
                    detection_count
                ),

                normalization_applied=True,

                high_pass_cutoff_hz=(
                    service
                    .audio_processing
                    .highpass_cutoff
                ),
            )
        ),

        rois=(
            roi_responses
        ),
    )


# ============================================================
# Analysis history
# ============================================================


@router.get(
    "",
    response_model=PaginatedResponse[
        AnalysisSummaryResponse
    ],
)
async def list_analyses(
    session: DatabaseSession,

    page: Annotated[
        int,
        Query(
            ge=1,
        ),
    ] = 1,

    page_size: Annotated[
        int,
        Query(
            ge=1,
            le=100,
        ),
    ] = 20,
) -> PaginatedResponse[
    AnalysisSummaryResponse
]:
    """
    Return previous manual-audio analysis sessions.
    """

    manual_device = (
        await get_or_create_manual_device(
            session
        )
    )

    base_conditions = [
        Recording.device_id
        == manual_device.id,

        Recording.capture_session_id
        .is_not(
            None
        ),
    ]

    count_statement = (
        select(
            func.count(
                func.distinct(
                    Recording.capture_session_id
                )
            )
        )
        .where(
            *base_conditions
        )
    )

    total_items = (
        await session.scalar(
            count_statement
        )
    ) or 0

    offset = (
        page - 1
    ) * page_size

    sessions_statement = (
        select(
            Recording.capture_session_id,
            func.min(
                Recording.original_filename
            ).label(
                "original_filename"
            ),
            func.min(
                Recording.capture_started_at
            ).label(
                "capture_started_at"
            ),
            func.count(
                func.distinct(
                    Recording.id
                )
            ).label(
                "roi_count"
            ),
            func.count(
                Detection.id
            ).label(
                "detection_count"
            ),
        )
        .outerjoin(
            Detection,
            Detection.recording_id
            == Recording.id,
        )
        .where(
            *base_conditions
        )
        .group_by(
            Recording.capture_session_id
        )
        .order_by(
            func.min(
                Recording.capture_started_at
            ).desc()
        )
        .offset(
            offset
        )
        .limit(
            page_size
        )
    )

    result = await session.execute(
        sessions_statement
    )

    items = [
        AnalysisSummaryResponse(
            capture_session_id=(
                row.capture_session_id
            ),

            original_filename=(
                row.original_filename
            ),

            capture_started_at=(
                row.capture_started_at
            ),

            roi_count=(
                row.roi_count
            ),

            detection_count=(
                row.detection_count
            ),
        )

        for row
        in result.all()
    ]

    total_pages = (
        math.ceil(
            total_items
            / page_size
        )
        if total_items > 0
        else 0
    )

    return PaginatedResponse[
        AnalysisSummaryResponse
    ](
        items=items,

        pagination=(
            PaginationMetadata(
                page=page,
                page_size=page_size,
                total_items=(
                    total_items
                ),
                total_pages=(
                    total_pages
                ),
            )
        ),
    )


# ============================================================
# Visualization data
# ============================================================


@router.get(
    "/{capture_session_id}/visualization",
    response_model=(
        AnalysisVisualizationResponse
    ),
)
async def get_analysis_visualization(
    capture_session_id: uuid.UUID,
    session: DatabaseSession,
) -> AnalysisVisualizationResponse:
    """
    Regenerate downsampled waveform and energy information from
    the stored original WAV for frontend visualization.
    """

    service = (
        ManualAnalysisService(
            session
        )
    )

    recordings = (
        await service.get_session_recordings(
            capture_session_id
        )
    )

    if not recordings:
        raise RecordingNotFoundError(
            "Manual analysis session "
            f"'{capture_session_id}' was not found."
        )

    original_path = (
        service.get_original_audio_path(
            capture_session_id
        )
    )

    if not original_path.exists():
        raise InvalidAudioFileError(
            "Stored source audio for this analysis "
            "session could not be found."
        )

    processing = (
        await asyncio.to_thread(
            service.audio_processing.process,
            original_path,
        )
    )

    visualization_rois = [
        AnalysisVisualizationROIResponse(
            recording_id=(
                recording.id
            ),

            snippet_sequence=(
                recording.snippet_sequence
                if recording.snippet_sequence
                is not None
                else 0
            ),

            start_time_seconds=float(
                recording.roi_start_seconds
                or 0.0
            ),

            end_time_seconds=float(
                recording.roi_end_seconds
                or 0.0
            ),
        )
        for recording
        in recordings
    ]

    # --------------------------------------------------------
    # Keep frontend payload reasonably small
    # --------------------------------------------------------

    waveform = (
        processing.normalized_audio
    )

    maximum_waveform_points = (
        3000
    )

    waveform_step = max(
        1,
        int(
            math.ceil(
                len(
                    waveform
                )
                / maximum_waveform_points
            )
        ),
    )

    waveform_indices = np.arange(
        0,
        len(
            waveform
        ),
        waveform_step,
    )

    waveform_values = (
        waveform[
            waveform_indices
        ]
    )

    waveform_times = (
        waveform_indices
        / processing.sample_rate
    )

    maximum_energy_points = (
        3000
    )

    energy_step = max(
        1,
        int(
            math.ceil(
                len(
                    processing.energy
                )
                / maximum_energy_points
            )
        ),
    )

    return (
        AnalysisVisualizationResponse(
            capture_session_id=(
                capture_session_id
            ),

            waveform_times=[
                float(
                    value
                )
                for value
                in waveform_times
            ],

            waveform_values=[
                float(
                    value
                )
                for value
                in waveform_values
            ],

            energy_times=[
                float(
                    value
                )
                for value
                in (
                    processing.energy_times[
                        ::energy_step
                    ]
                )
            ],

            energy_values=[
                float(
                    value
                )
                for value
                in (
                    processing.energy[
                        ::energy_step
                    ]
                )
            ],

            energy_threshold=float(
                processing.energy_threshold
            ),

            rois=(
                visualization_rois
            ),
        )
    )