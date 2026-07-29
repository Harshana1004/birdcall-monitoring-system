from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import (
    BaseSettings,
    SettingsConfigDict,
)


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    app_name: str = "BirdCall Monitoring Backend"
    app_version: str = "0.1.0"
    app_environment: str = "development"
    debug: bool = False

    database_url: str

    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
    ]

    audio_storage_directory: Path = Path(
        "storage/audio"
    )

    max_upload_size_mb: int = Field(
        default=25,
        ge=1,
        le=500,
    )

    allowed_audio_extensions: str = "wav"

    roi_duration_tolerance_seconds: float = Field(
        default=0.25,
        ge=0.0,
        le=5.0,
        description=(
            "Maximum permitted difference between the ROI "
            "metadata duration and actual WAV duration."
        ),
    )

    max_roi_duration_seconds: float = Field(
        default=30.0,
        gt=0.0,
        le=300.0,
        description=(
            "Maximum accepted duration of one ESP32-generated "
            "ROI audio snippet."
        ),
    )

    max_edge_metadata_size_bytes: int = Field(
        default=8192,
        ge=256,
        le=1_048_576,
        description=(
            "Maximum UTF-8 size of the edge-processing metadata "
            "JSON form field."
        ),
    )

    birdnet_model_name: str = "BirdNET"
    birdnet_model_version: str = "2.4"
    birdnet_backend: str = "tf"

    birdnet_min_confidence: float = Field(
        default=0.25,
        ge=0.0,
        le=1.0,
    )

    birdnet_max_predictions_per_interval: int = Field(
        default=5,
        ge=1,
        le=100,
    )

    birdnet_model_loading_timeout_seconds: float = Field(
        default=120.0,
        gt=0,
    )

    default_timezone: str = "Asia/Colombo"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def allowed_audio_extension_set(self) -> set[str]:
        """
        Return normalized audio extensions configured through
        ALLOWED_AUDIO_EXTENSIONS.

        Example environment value:

        ALLOWED_AUDIO_EXTENSIONS=wav,flac
        """

        return {
            extension.strip().lower().lstrip(".")
            for extension in self.allowed_audio_extensions.split(",")
            if extension.strip()
        }

    @property
    def max_upload_size_bytes(self) -> int:
        """Return the configured upload limit in bytes."""

        return self.max_upload_size_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    """Return one cached settings instance."""

    return Settings()


settings = get_settings()