import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Generic, Self, TypeVar

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from src.core.config import settings
from src.models import ProcessingStatus


# ============================================================
# Common schemas
# ============================================================


DataType = TypeVar(
    "DataType"
)


class ErrorResponse(BaseModel):
    error: str
    message: str


class PaginationMetadata(BaseModel):
    page: int = Field(
        ge=1
    )

    page_size: int = Field(
        ge=1
    )

    total_items: int = Field(
        ge=0
    )

    total_pages: int = Field(
        ge=0
    )


class PaginatedResponse(
    BaseModel,
    Generic[DataType],
):
    items: list[DataType]

    pagination: (
        PaginationMetadata
    )


# ============================================================
# Device schemas
# ============================================================


class DeviceBase(BaseModel):
    device_code: str = Field(
        min_length=1,
        max_length=50,
        examples=[
            "NODE-001"
        ],
    )

    name: str = Field(
        min_length=1,
        max_length=120,
        examples=[
            "Sinharaja Forest Node"
        ],
    )

    description: str | None = Field(
        default=None,
        max_length=2000,
    )

    latitude: Decimal | None = Field(
        default=None,
        ge=-90,
        le=90,
    )

    longitude: Decimal | None = Field(
        default=None,
        ge=-180,
        le=180,
    )

    installed_at: (
        datetime | None
    ) = None

    is_active: bool = True

    @field_validator(
        "device_code"
    )
    @classmethod
    def normalize_device_code(
        cls,
        value: str,
    ) -> str:
        normalized = (
            value
            .strip()
            .upper()
        )

        if not normalized:
            raise ValueError(
                "Device code cannot be blank."
            )

        return normalized

    @field_validator(
        "name"
    )
    @classmethod
    def normalize_name(
        cls,
        value: str,
    ) -> str:
        normalized = (
            value.strip()
        )

        if not normalized:
            raise ValueError(
                "Device name cannot be blank."
            )

        return normalized


class DeviceCreate(
    DeviceBase
):
    pass


class DeviceUpdate(BaseModel):
    device_code: str | None = Field(
        default=None,
        min_length=1,
        max_length=50,
    )

    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=120,
    )

    description: str | None = Field(
        default=None,
        max_length=2000,
    )

    latitude: Decimal | None = Field(
        default=None,
        ge=-90,
        le=90,
    )

    longitude: Decimal | None = Field(
        default=None,
        ge=-180,
        le=180,
    )

    installed_at: (
        datetime | None
    ) = None

    is_active: bool | None = None

    @field_validator(
        "device_code"
    )
    @classmethod
    def normalize_optional_device_code(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        normalized = (
            value
            .strip()
            .upper()
        )

        if not normalized:
            raise ValueError(
                "Device code cannot be blank."
            )

        return normalized

    @field_validator(
        "name"
    )
    @classmethod
    def normalize_optional_name(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        normalized = (
            value.strip()
        )

        if not normalized:
            raise ValueError(
                "Device name cannot be blank."
            )

        return normalized


class DeviceResponse(
    DeviceBase
):
    model_config = ConfigDict(
        from_attributes=True,
    )

    id: uuid.UUID
    created_at: datetime
    updated_at: datetime


# ============================================================
# Recording schemas
# ============================================================


class RecordingUploadMetadata(
    BaseModel
):
    """
    Validated metadata supplied by an ESP32 for one ROI snippet.

    Audio properties such as duration, sample rate and channel
    count are not accepted because the backend derives them from
    the uploaded WAV file.
    """

    model_config = ConfigDict(
        extra="forbid",
    )

    client_upload_id: uuid.UUID

    capture_session_id: (
        uuid.UUID
    )

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

    edge_processing_metadata: dict[
        str,
        Any,
    ] = Field(
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

    @field_validator(
        "capture_started_at"
    )
    @classmethod
    def validate_timezone(
        cls,
        value: datetime,
    ) -> datetime:
        if (
            value.tzinfo is None
            or value.utcoffset()
            is None
        ):
            raise ValueError(
                "capture_started_at must include "
                "a timezone offset."
            )

        return value

    @field_validator(
        "edge_processing_version"
    )
    @classmethod
    def normalize_edge_processing_version(
        cls,
        value: str,
    ) -> str:
        normalized_value = (
            value.strip()
        )

        if not normalized_value:
            raise ValueError(
                "edge_processing_version "
                "cannot be blank."
            )

        return normalized_value

    @model_validator(
        mode="after"
    )
    def validate_roi_interval(
        self,
    ) -> Self:
        if (
            self.roi_end_seconds
            <= self.roi_start_seconds
        ):
            raise ValueError(
                "roi_end_seconds must be "
                "greater than roi_start_seconds."
            )

        roi_duration = (
            self.roi_end_seconds
            - self.roi_start_seconds
        )

        if (
            roi_duration
            > settings.max_roi_duration_seconds
        ):
            raise ValueError(
                "ROI duration cannot exceed "
                f"{settings.max_roi_duration_seconds} "
                "seconds."
            )

        return self

    @property
    def roi_duration_seconds(
        self,
    ) -> float:
        return (
            self.roi_end_seconds
            - self.roi_start_seconds
        )


class RecordingResponse(
    BaseModel
):
    """
    Full public representation of one ROI recording.
    """

    model_config = ConfigDict(
        from_attributes=True,
    )

    id: uuid.UUID
    device_id: uuid.UUID

    client_upload_id: (
        uuid.UUID | None
    )

    capture_session_id: (
        uuid.UUID | None
    )

    snippet_sequence: (
        int | None
    )

    original_filename: str
    stored_filename: str
    checksum_sha256: str
    file_size_bytes: int

    capture_started_at: (
        datetime | None
    )

    recorded_at: datetime
    uploaded_at: datetime

    roi_start_seconds: (
        float | None
    )

    roi_end_seconds: (
        float | None
    )

    duration_seconds: float
    sample_rate: int
    channel_count: int

    latitude: Decimal | None
    longitude: Decimal | None

    edge_processing_version: (
        str | None
    )

    edge_processing_metadata: dict[
        str,
        Any,
    ]

    processing_status: (
        ProcessingStatus
    )

    processing_started_at: (
        datetime | None
    )

    processed_at: (
        datetime | None
    )

    processing_error: (
        str | None
    )


class RecordingSummaryResponse(
    BaseModel
):
    """
    Reduced recording representation for list endpoints.
    """

    model_config = ConfigDict(
        from_attributes=True,
    )

    id: uuid.UUID
    device_id: uuid.UUID

    capture_session_id: (
        uuid.UUID | None
    )

    snippet_sequence: (
        int | None
    )

    original_filename: str

    recorded_at: datetime
    uploaded_at: datetime

    roi_start_seconds: (
        float | None
    )

    roi_end_seconds: (
        float | None
    )

    duration_seconds: float
    sample_rate: int
    channel_count: int

    processing_status: (
        ProcessingStatus
    )


class RecordingUploadResponse(
    BaseModel
):
    """
    Response returned for a new upload or idempotent retry.
    """

    message: str
    created: bool
    recording: RecordingResponse


# ============================================================
# Detection schemas
# ============================================================


class DetectionCreate(BaseModel):
    """
    Validated data required to create one BirdNET detection.
    """

    scientific_name: str = Field(
        min_length=1,
        max_length=180,
    )

    common_name: str = Field(
        min_length=1,
        max_length=180,
    )

    confidence: float = Field(
        ge=0,
        le=1,
    )

    start_time_seconds: float = Field(
        ge=0,
    )

    end_time_seconds: float = Field(
        gt=0,
    )

    model_name: str = Field(
        min_length=1,
        max_length=100,
    )

    model_version: str = Field(
        min_length=1,
        max_length=50,
    )

    @model_validator(
        mode="after"
    )
    def validate_interval(
        self,
    ) -> Self:
        if (
            self.end_time_seconds
            <= self.start_time_seconds
        ):
            raise ValueError(
                "end_time_seconds must be greater "
                "than start_time_seconds."
            )

        return self


class DetectionResponse(
    DetectionCreate
):
    """
    Complete public representation of one detection.
    """

    model_config = ConfigDict(
        from_attributes=True,
    )

    id: uuid.UUID
    recording_id: uuid.UUID
    created_at: datetime


class DetectionSummaryResponse(
    BaseModel
):
    """
    Compact detection representation for paginated lists.
    """

    model_config = ConfigDict(
        from_attributes=True,
    )

    id: uuid.UUID
    recording_id: uuid.UUID

    scientific_name: str
    common_name: str

    confidence: float = Field(
        ge=0,
        le=1,
    )

    start_time_seconds: float = Field(
        ge=0,
    )

    end_time_seconds: float = Field(
        gt=0,
    )

    created_at: datetime