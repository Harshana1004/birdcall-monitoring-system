from __future__ import annotations

import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import (
    JSONB,
    UUID,
)
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
    relationship,
)

from src.database import Base


# ============================================================
# Enums
# ============================================================


class ProcessingStatus(str, enum.Enum):
    """
    Current BirdNET processing state of an ROI recording.
    """

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


# ============================================================
# Device
# ============================================================


class Device(Base):
    """
    Remote bird-call monitoring device.

    One device may upload many ROI recordings.
    """

    __tablename__ = "devices"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    device_code: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        unique=True,
    )

    name: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    latitude: Mapped[Decimal | None] = mapped_column(
        Numeric(9, 6),
        nullable=True,
    )

    longitude: Mapped[Decimal | None] = mapped_column(
        Numeric(9, 6),
        nullable=True,
    )

    installed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    recordings: Mapped[list["Recording"]] = relationship(
        back_populates="device",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        CheckConstraint(
            (
                "latitude IS NULL "
                "OR latitude BETWEEN -90 AND 90"
            ),
            name="ck_devices_valid_latitude",
        ),
        CheckConstraint(
            (
                "longitude IS NULL "
                "OR longitude BETWEEN -180 AND 180"
            ),
            name="ck_devices_valid_longitude",
        ),
        Index(
            "ix_devices_is_active",
            "is_active",
        ),
    )


# ============================================================
# Recording
# ============================================================


class Recording(Base):
    """
    One audio ROI snippet uploaded by an edge device.

    A Recording does not represent the complete continuous
    capture. Multiple Recording rows may belong to the same
    capture session.
    """

    __tablename__ = "recordings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    device_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "devices.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )

    # --------------------------------------------------------
    # Upload / capture identification
    # --------------------------------------------------------

    client_upload_id: Mapped[
        uuid.UUID | None
    ] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )

    capture_session_id: Mapped[
        uuid.UUID | None
    ] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )

    snippet_sequence: Mapped[
        int | None
    ] = mapped_column(
        Integer,
        nullable=True,
    )

    # --------------------------------------------------------
    # File information
    # --------------------------------------------------------

    original_filename: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    stored_filename: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
    )

    file_path: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        unique=True,
    )

    checksum_sha256: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    file_size_bytes: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    # --------------------------------------------------------
    # Capture timing
    # --------------------------------------------------------

    capture_started_at: Mapped[
        datetime | None
    ] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    roi_start_seconds: Mapped[
        float | None
    ] = mapped_column(
        Float,
        nullable=True,
    )

    roi_end_seconds: Mapped[
        float | None
    ] = mapped_column(
        Float,
        nullable=True,
    )

    # --------------------------------------------------------
    # BirdNET processing lifecycle
    # --------------------------------------------------------

    processing_started_at: Mapped[
        datetime | None
    ] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    processed_at: Mapped[
        datetime | None
    ] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    processing_status: Mapped[
        ProcessingStatus
    ] = mapped_column(
        Enum(
            ProcessingStatus,
            name="processing_status",
            values_callable=lambda enum_class: [
                member.value
                for member in enum_class
            ],
        ),
        nullable=False,
        default=ProcessingStatus.PENDING,
        server_default=(
            ProcessingStatus.PENDING.value
        ),
    )

    processing_error: Mapped[
        str | None
    ] = mapped_column(
        Text,
        nullable=True,
    )

    # --------------------------------------------------------
    # Audio properties
    # --------------------------------------------------------

    duration_seconds: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    sample_rate: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    channel_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # --------------------------------------------------------
    # Location
    # --------------------------------------------------------

    latitude: Mapped[
        Decimal | None
    ] = mapped_column(
        Numeric(9, 6),
        nullable=True,
    )

    longitude: Mapped[
        Decimal | None
    ] = mapped_column(
        Numeric(9, 6),
        nullable=True,
    )

    # --------------------------------------------------------
    # Edge-processing metadata
    # --------------------------------------------------------

    edge_processing_version: Mapped[
        str | None
    ] = mapped_column(
        String(100),
        nullable=True,
    )

    edge_processing_metadata: Mapped[
        dict[str, Any]
    ] = mapped_column(
        MutableDict.as_mutable(
            JSONB
        ),
        nullable=False,
        default=dict,
        server_default=text(
            "'{}'::jsonb"
        ),
    )

    # --------------------------------------------------------
    # Relationships
    # --------------------------------------------------------

    device: Mapped["Device"] = relationship(
        back_populates="recordings",
    )

    detections: Mapped[
        list["Detection"]
    ] = relationship(
        back_populates="recording",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    # --------------------------------------------------------
    # Constraints / indexes
    # --------------------------------------------------------

    __table_args__ = (
        UniqueConstraint(
            "device_id",
            "capture_session_id",
            "checksum_sha256",
            name=(
                "uq_recordings_device_session_checksum"
            ),
        ),

        UniqueConstraint(
            "device_id",
            "client_upload_id",
            name=(
                "uq_recordings_device_client_upload"
            ),
        ),

        CheckConstraint(
            "file_size_bytes > 0",
            name=(
                "ck_recordings_positive_file_size"
            ),
        ),

        CheckConstraint(
            "duration_seconds > 0",
            name=(
                "ck_recordings_positive_duration"
            ),
        ),

        CheckConstraint(
            "sample_rate > 0",
            name=(
                "ck_recordings_positive_sample_rate"
            ),
        ),

        CheckConstraint(
            "channel_count > 0",
            name=(
                "ck_recordings_positive_channel_count"
            ),
        ),

        CheckConstraint(
            (
                "snippet_sequence IS NULL "
                "OR snippet_sequence >= 0"
            ),
            name=(
                "ck_recordings_nonnegative_"
                "snippet_sequence"
            ),
        ),

        CheckConstraint(
            (
                "("
                "roi_start_seconds IS NULL "
                "AND roi_end_seconds IS NULL"
                ") "
                "OR "
                "("
                "roi_start_seconds >= 0 "
                "AND roi_end_seconds "
                "> roi_start_seconds"
                ")"
            ),
            name=(
                "ck_recordings_valid_roi_interval"
            ),
        ),

        CheckConstraint(
            (
                "latitude IS NULL "
                "OR latitude BETWEEN -90 AND 90"
            ),
            name=(
                "ck_recordings_valid_latitude"
            ),
        ),

        CheckConstraint(
            (
                "longitude IS NULL "
                "OR longitude BETWEEN -180 AND 180"
            ),
            name=(
                "ck_recordings_valid_longitude"
            ),
        ),

        Index(
            "ix_recordings_device_recorded_at",
            "device_id",
            "recorded_at",
        ),

        Index(
            "ix_recordings_device_capture_session",
            "device_id",
            "capture_session_id",
        ),

        Index(
            "ix_recordings_capture_session_sequence",
            "capture_session_id",
            "snippet_sequence",
        ),

        Index(
            "ix_recordings_processing_status",
            "processing_status",
        ),

        Index(
            "ix_recordings_recorded_at",
            "recorded_at",
        ),
    )


# ============================================================
# Detection
# ============================================================


class Detection(Base):
    """
    One BirdNET species prediction belonging to a recording.
    """

    __tablename__ = "detections"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    recording_id: Mapped[
        uuid.UUID
    ] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "recordings.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )

    scientific_name: Mapped[str] = mapped_column(
        String(180),
        nullable=False,
    )

    common_name: Mapped[str] = mapped_column(
        String(180),
        nullable=False,
    )

    confidence: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    start_time_seconds: Mapped[
        float
    ] = mapped_column(
        Float,
        nullable=False,
    )

    end_time_seconds: Mapped[
        float
    ] = mapped_column(
        Float,
        nullable=False,
    )

    model_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    model_version: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    created_at: Mapped[
        datetime
    ] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    recording: Mapped[
        "Recording"
    ] = relationship(
        back_populates="detections",
    )

    __table_args__ = (
        CheckConstraint(
            "confidence BETWEEN 0 AND 1",
            name=(
                "ck_detections_valid_confidence"
            ),
        ),

        CheckConstraint(
            "start_time_seconds >= 0",
            name=(
                "ck_detections_nonnegative_start"
            ),
        ),

        CheckConstraint(
            (
                "end_time_seconds "
                "> start_time_seconds"
            ),
            name=(
                "ck_detections_valid_interval"
            ),
        ),

        UniqueConstraint(
            "recording_id",
            "scientific_name",
            "start_time_seconds",
            "end_time_seconds",
            "model_name",
            "model_version",
            name=(
                "uq_detections_recording_"
                "species_interval_model"
            ),
        ),

        Index(
            "ix_detections_recording_id",
            "recording_id",
        ),

        Index(
            "ix_detections_scientific_name",
            "scientific_name",
        ),

        Index(
            "ix_detections_common_name",
            "common_name",
        ),

        Index(
            "ix_detections_confidence",
            "confidence",
        ),

        Index(
            "ix_detections_created_at",
            "created_at",
        ),
    )