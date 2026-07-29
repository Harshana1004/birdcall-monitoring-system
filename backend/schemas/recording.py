import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from core.config import settings
from models.recording import ProcessingStatus


class RecordingUploadMetadata(BaseModel):
    """
    Validated metadata supplied by an ESP32 for one ROI snippet.

    Audio properties such as duration, sample rate and channel count
    are not accepted here because the backend derives them directly
    from the uploaded WAV file.
    """

    model_config = ConfigDict(
        extra="forbid",
    )

    client_upload_id: uuid.UUID
    capture_session_id: uuid.UUID

    snippet_sequence: int = Field(
        ge=0,
    )

    capture_started_at: datetime

    roi_start_seconds: float = Field(
        ge=0,
    )

    roi_end_seconds: float = Field(
        gt=0,
    )

    edge_processing_version: str = Field(
        min_length=1,
        max_length=100,
    )

    edge_processing_metadata: dict[str, Any] = Field(
        default_factory=dict,
    )

    latitude: Decimal | None = Field(
        default=None,
        ge=Decimal("-90"),
        le=Decimal("90"),
    )

    longitude: Decimal | None = Field(
        default=None,
        ge=Decimal("-180"),
        le=Decimal("180"),
    )

    @field_validator("capture_started_at")
    @classmethod
    def validate_timezone(
        cls,
        value: datetime,
    ) -> datetime:
        if (
            value.tzinfo is None
            or value.utcoffset() is None
        ):
            raise ValueError(
                "capture_started_at must include a timezone offset."
            )

        return value

    @field_validator("edge_processing_version")
    @classmethod
    def normalize_edge_processing_version(
        cls,
        value: str,
    ) -> str:
        normalized_value = value.strip()

        if not normalized_value:
            raise ValueError(
                "edge_processing_version cannot be blank."
            )

        return normalized_value

    @model_validator(mode="after")
    def validate_roi_interval(
        self,
    ) -> Self:
        if self.roi_end_seconds <= self.roi_start_seconds:
            raise ValueError(
                "roi_end_seconds must be greater than "
                "roi_start_seconds."
            )

        roi_duration = (
            self.roi_end_seconds
            - self.roi_start_seconds
        )

        if roi_duration > settings.max_roi_duration_seconds:
            raise ValueError(
                "ROI duration cannot exceed "
                f"{settings.max_roi_duration_seconds} seconds."
            )

        return self

    @property
    def roi_duration_seconds(self) -> float:
        return (
            self.roi_end_seconds
            - self.roi_start_seconds
        )


class RecordingResponse(BaseModel):
    """Full public representation of an ROI recording."""

    model_config = ConfigDict(
        from_attributes=True,
    )

    id: uuid.UUID
    device_id: uuid.UUID

    client_upload_id: uuid.UUID | None
    capture_session_id: uuid.UUID | None
    snippet_sequence: int | None

    original_filename: str
    stored_filename: str
    checksum_sha256: str
    file_size_bytes: int

    capture_started_at: datetime | None
    recorded_at: datetime
    uploaded_at: datetime

    roi_start_seconds: float | None
    roi_end_seconds: float | None

    duration_seconds: float
    sample_rate: int
    channel_count: int

    latitude: Decimal | None
    longitude: Decimal | None

    edge_processing_version: str | None
    edge_processing_metadata: dict[str, Any]

    processing_status: ProcessingStatus
    processing_started_at: datetime | None
    processed_at: datetime | None
    processing_error: str | None


class RecordingSummaryResponse(BaseModel):
    """Reduced recording representation for list endpoints."""

    model_config = ConfigDict(
        from_attributes=True,
    )

    id: uuid.UUID
    device_id: uuid.UUID

    capture_session_id: uuid.UUID | None
    snippet_sequence: int | None

    original_filename: str

    recorded_at: datetime
    uploaded_at: datetime

    roi_start_seconds: float | None
    roi_end_seconds: float | None

    duration_seconds: float
    sample_rate: int
    channel_count: int

    processing_status: ProcessingStatus


class RecordingUploadResponse(BaseModel):
    """Response returned for a new upload or idempotent retry."""

    message: str
    created: bool
    recording: RecordingResponse