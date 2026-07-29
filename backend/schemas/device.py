import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DeviceBase(BaseModel):
    device_code: str = Field(
        min_length=1,
        max_length=50,
        examples=["NODE-001"],
    )

    name: str = Field(
        min_length=1,
        max_length=120,
        examples=["Sinharaja Forest Node"],
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

    installed_at: datetime | None = None
    is_active: bool = True

    @field_validator("device_code")
    @classmethod
    def normalize_device_code(cls, value: str) -> str:
        normalized = value.strip().upper()

        if not normalized:
            raise ValueError("Device code cannot be blank.")

        return normalized

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = value.strip()

        if not normalized:
            raise ValueError("Device name cannot be blank.")

        return normalized


class DeviceCreate(DeviceBase):
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

    installed_at: datetime | None = None
    is_active: bool | None = None

    @field_validator("device_code")
    @classmethod
    def normalize_optional_device_code(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        normalized = value.strip().upper()

        if not normalized:
            raise ValueError("Device code cannot be blank.")

        return normalized

    @field_validator("name")
    @classmethod
    def normalize_optional_name(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        normalized = value.strip()

        if not normalized:
            raise ValueError("Device name cannot be blank.")

        return normalized


class DeviceResponse(DeviceBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    updated_at: datetime