import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Generic, Literal, Self, TypeVar

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
    model_validator,
)

from src.core.config import settings
from src.core.regions import normalize_region_code
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
# User / authentication schemas
# ============================================================


class UserResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
    )

    id: uuid.UUID
    email: str
    display_name: str | None
    is_admin: bool
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None


class RegisterRequest(BaseModel):
    email: EmailStr

    password: str = Field(
        min_length=1,
        max_length=128,
    )

    display_name: str | None = Field(
        default=None,
        max_length=120,
    )

    @field_validator(
        "password"
    )
    @classmethod
    def validate_password_length(
        cls,
        value: str,
    ) -> str:
        if len(value) < settings.password_min_length:
            raise ValueError(
                "Password must be at least "
                f"{settings.password_min_length} characters."
            )

        return value

    @field_validator(
        "display_name"
    )
    @classmethod
    def normalize_display_name(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        normalized = value.strip()
        return normalized or None


class LoginRequest(BaseModel):
    email: EmailStr

    password: str = Field(
        min_length=1,
        max_length=128,
    )


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_at: datetime
    user: UserResponse


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(
        min_length=1,
        max_length=128,
    )

    new_password: str = Field(
        min_length=1,
        max_length=128,
    )

    @field_validator(
        "new_password"
    )
    @classmethod
    def validate_new_password_length(
        cls,
        value: str,
    ) -> str:
        if len(value) < settings.password_min_length:
            raise ValueError(
                "Password must be at least "
                f"{settings.password_min_length} characters."
            )

        return value


class ProfileUpdateRequest(BaseModel):
    display_name: str | None = Field(
        default=None,
        max_length=120,
    )


class UserAdminUpdate(BaseModel):
    is_admin: bool | None = None
    is_active: bool | None = None


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

    # Province or district for BirdNET's location filter (see
    # src/core/regions.py); used when latitude/longitude are unset.
    region_code: str | None = Field(
        default=None,
        max_length=8,
        examples=[
            "LK-21"
        ],
    )

    is_active: bool = True

    @field_validator(
        "region_code"
    )
    @classmethod
    def validate_region_code(
        cls,
        value: str | None,
    ) -> str | None:
        return normalize_region_code(value)

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

    # Province or district for BirdNET's location filter (see
    # src/core/regions.py); used when latitude/longitude are unset.
    region_code: str | None = Field(
        default=None,
        max_length=8,
        examples=[
            "LK-21"
        ],
    )

    is_active: bool | None = None

    # Admin only: visible (read-only) to every signed-in user.
    is_shared: bool | None = None

    @field_validator(
        "region_code"
    )
    @classmethod
    def validate_optional_region_code(
        cls,
        value: str | None,
    ) -> str | None:
        return normalize_region_code(value)

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


class DeviceOwnerSummary(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str | None


class DeviceResponse(
    DeviceBase
):
    model_config = ConfigDict(
        from_attributes=True,
    )

    id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    # e.g. "Kandy District"; None when region_code is unset.
    region_name: str | None = None

    is_shared: bool = False
    owner: DeviceOwnerSummary | None = None
    claimed_at: datetime | None = None
    has_claim_code: bool = False

    # Activity (filled by list/detail endpoints).
    recording_count: int = 0
    detection_count: int = 0
    last_recording_at: datetime | None = None


class DeviceCreatedResponse(BaseModel):
    """
    A newly registered device plus its claim code. The code is
    only ever shown here (and when regenerated); the server keeps
    just a hash.
    """

    device: DeviceResponse
    claim_code: str


class ClaimCodeResponse(BaseModel):
    device_id: uuid.UUID
    device_code: str
    claim_code: str


class DeviceClaimRequest(BaseModel):
    device_code: str = Field(
        min_length=1,
        max_length=50,
    )

    claim_code: str = Field(
        min_length=1,
        max_length=40,
    )

    @field_validator(
        "device_code"
    )
    @classmethod
    def normalize_claim_device_code(
        cls,
        value: str,
    ) -> str:
        return value.strip().upper()


class DeviceOwnerAssignment(BaseModel):
    """
    Admin: give a device to a user (by id or email), or clear the
    owner with both fields null.
    """

    owner_id: uuid.UUID | None = None
    owner_email: EmailStr | None = None


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

    species_filter: (
        str | None
    ) = None


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


# ============================================================
# Manual audio analysis
# ============================================================


class AnalysisDetectionResponse(BaseModel):
    """
    One persisted BirdNET prediction produced from a manually
    generated ROI.
    """

    model_config = ConfigDict(
        from_attributes=True,
    )

    id: uuid.UUID

    scientific_name: str
    common_name: str

    confidence: float = Field(
        ge=0.0,
        le=1.0,
    )

    start_time_seconds: float = Field(
        ge=0.0,
    )

    end_time_seconds: float = Field(
        gt=0.0,
    )

    model_name: str
    model_version: str


class AnalysisROIResponse(BaseModel):
    """
    One detected acoustic ROI belonging to a manual-analysis
    session.
    """

    recording_id: uuid.UUID

    snippet_sequence: int = Field(
        ge=0,
    )

    roi_start_seconds: float = Field(
        ge=0.0,
    )

    roi_end_seconds: float = Field(
        gt=0.0,
    )

    original_duration_seconds: float = Field(
        gt=0.0,
    )

    stored_duration_seconds: float = Field(
        gt=0.0,
    )

    processing_status: ProcessingStatus

    detections: list[
        AnalysisDetectionResponse
    ] = Field(
        default_factory=list
    )


class AnalysisProcessingResponse(BaseModel):
    """
    Summary of the backend preprocessing and classification
    operation.
    """

    sample_rate: int = Field(
        gt=0,
    )

    duration_seconds: float = Field(
        gt=0.0,
    )

    energy_threshold: float = Field(
        ge=0.0,
    )

    roi_count: int = Field(
        ge=0,
    )

    detection_count: int = Field(
        ge=0,
    )

    normalization_applied: bool

    high_pass_cutoff_hz: float = Field(
        gt=0.0,
    )


class AnalysisResponse(BaseModel):
    """
    Complete representation of one manual audio-analysis
    session.
    """

    capture_session_id: uuid.UUID

    original_filename: str

    capture_started_at: datetime

    processing: (
        AnalysisProcessingResponse
    )

    rois: list[
        AnalysisROIResponse
    ] = Field(
        default_factory=list
    )


class AnalysisSummaryResponse(BaseModel):
    """
    Compact representation used for analysis history.
    """

    capture_session_id: uuid.UUID

    original_filename: str

    capture_started_at: datetime

    roi_count: int = Field(
        ge=0,
    )

    detection_count: int = Field(
        ge=0,
    )


class AnalysisVisualizationROIResponse(
    BaseModel
):
    """
    Lightweight ROI interval used for frontend visualization.
    """

    recording_id: uuid.UUID

    snippet_sequence: int = Field(
        ge=0,
    )

    start_time_seconds: float = Field(
        ge=0.0,
    )

    end_time_seconds: float = Field(
        gt=0.0,
    )


class AnalysisVisualizationResponse(
    BaseModel
):
    """
    Downsampled waveform and short-time-energy information
    regenerated from the stored original WAV.

    These arrays are intentionally not stored in PostgreSQL.
    """

    capture_session_id: uuid.UUID

    waveform_times: list[
        float
    ]

    waveform_values: list[
        float
    ]

    energy_times: list[
        float
    ]

    energy_values: list[
        float
    ]

    energy_threshold: float

    rois: list[
        AnalysisVisualizationROIResponse
    ]


# ============================================================
# Device activity: timelines, detection feed, summaries
# ============================================================


class TimelineDetection(BaseModel):
    """
    One BirdNET detection with its real-world time.

    detected_at = recording.recorded_at + start_time_seconds;
    device ROIs are not padded, so BirdNET's offsets are offsets
    into the ROI itself.
    """

    id: uuid.UUID
    scientific_name: str
    common_name: str
    confidence: float
    start_time_seconds: float
    end_time_seconds: float
    detected_at: datetime


class TimelineRecording(BaseModel):
    """
    One ROI snippet with its detections, for device timelines.
    """

    id: uuid.UUID
    device_id: uuid.UUID
    capture_session_id: uuid.UUID | None
    snippet_sequence: int | None
    recorded_at: datetime
    uploaded_at: datetime
    duration_seconds: float
    roi_start_seconds: float | None
    roi_end_seconds: float | None
    processing_status: ProcessingStatus
    processing_error: str | None
    species_filter: str | None = None
    detections: list[
        TimelineDetection
    ] = Field(
        default_factory=list
    )


class DetectionFeedItem(TimelineDetection):
    """
    A detection plus where it came from, for feeds across devices.
    """

    recording_id: uuid.UUID
    recording_duration_seconds: float
    device_id: uuid.UUID
    device_code: str
    device_name: str


class SpeciesCount(BaseModel):
    scientific_name: str
    common_name: str
    detection_count: int
    max_confidence: float
    last_detected_at: datetime | None


class DailyActivity(BaseModel):
    """
    Counts for one calendar day in DEFAULT_TIMEZONE.
    """

    day: date
    recording_count: int
    detection_count: int


class DeviceSummaryResponse(BaseModel):
    device_id: uuid.UUID
    recording_count: int
    detection_count: int
    species_count: int
    first_recording_at: datetime | None
    last_recording_at: datetime | None
    top_species: list[SpeciesCount]
    daily_activity: list[DailyActivity]


class DashboardResponse(BaseModel):
    device_count: int
    active_device_count: int
    recording_count: int
    recordings_last_24h: int
    detection_count: int
    detections_last_24h: int
    species_count: int
    last_recording_at: datetime | None
    top_species: list[SpeciesCount]
    daily_activity: list[DailyActivity]
    recent_detections: list[DetectionFeedItem]