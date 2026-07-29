from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.db import Base

if TYPE_CHECKING:
    from models.recording import Recording


class Detection(Base):
    __tablename__ = "detections"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    recording_id: Mapped[uuid.UUID] = mapped_column(
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

    start_time_seconds: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    end_time_seconds: Mapped[float] = mapped_column(
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

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    recording: Mapped["Recording"] = relationship(
        back_populates="detections",
    )

    __table_args__ = (
        CheckConstraint(
            "confidence BETWEEN 0 AND 1",
            name="ck_detections_valid_confidence",
        ),
        CheckConstraint(
            "start_time_seconds >= 0",
            name="ck_detections_nonnegative_start",
        ),
        CheckConstraint(
            "end_time_seconds > start_time_seconds",
            name="ck_detections_valid_interval",
        ),
        UniqueConstraint(
            "recording_id",
            "scientific_name",
            "start_time_seconds",
            "end_time_seconds",
            "model_name",
            "model_version",
            name="uq_detections_recording_species_interval_model",
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