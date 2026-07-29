import uuid
from datetime import datetime

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)


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
    ) -> "DetectionCreate":
        if (
            self.end_time_seconds
            <= self.start_time_seconds
        ):
            raise ValueError(
                "end_time_seconds must be greater than "
                "start_time_seconds."
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