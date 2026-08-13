from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import (
    BaseSettings,
    SettingsConfigDict,
)


BACKEND_DIRECTORY = (
    Path(__file__).resolve().parents[2]
)

ENV_FILE = (
    BACKEND_DIRECTORY / ".env"
)


class Settings(BaseSettings):
    """Application configuration."""

    app_name: str = (
        "BirdCall Monitoring Backend"
    )

    app_version: str = "0.1.0"

    app_environment: str = (
        "development"
    )

    debug: bool = False

    database_url: str

    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
    ]

    audio_storage_directory: Path = (
        BACKEND_DIRECTORY
        / "storage"
        / "audio"
    )

    demo_storage_directory: Path = (
        BACKEND_DIRECTORY
        / "storage"
        / "demo"
    )

    max_upload_size_mb: int = Field(
        default=25,
        ge=1,
        le=500,
    )

    allowed_audio_extensions: str = (
        "wav"
    )

    roi_duration_tolerance_seconds: float = (
        Field(
            default=0.25,
            ge=0.0,
            le=5.0,
        )
    )

    max_roi_duration_seconds: float = (
        Field(
            default=30.0,
            gt=0.0,
            le=300.0,
        )
    )

    max_edge_metadata_size_bytes: int = (
        Field(
            default=8192,
            ge=256,
            le=1_048_576,
        )
    )

    # BirdNET
    birdnet_model_name: str = "BirdNET"
    birdnet_model_version: str = "2.4"
    birdnet_backend: str = "tf"

    birdnet_min_confidence: float = (
        Field(
            default=0.25,
            ge=0.0,
            le=1.0,
        )
    )

    birdnet_max_predictions_per_interval: int = (
        Field(
            default=5,
            ge=1,
            le=100,
        )
    )

    birdnet_model_loading_timeout_seconds: float = (
        Field(
            default=120.0,
            gt=0.0,
        )
    )

    # Mid-evaluation demonstration pipeline.
    #
    # This is NOT the final deployment architecture.
    # In the final system preprocessing runs on the ESP32.
    enable_demo_pipeline: bool = True

    default_timezone: str = (
        "Asia/Colombo"
    )

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def allowed_audio_extension_set(
        self,
    ) -> set[str]:
        return {
            extension.strip()
            .lower()
            .lstrip(".")
            for extension
            in self.allowed_audio_extensions.split(
                ","
            )
            if extension.strip()
        }

    @property
    def max_upload_size_bytes(
        self,
    ) -> int:
        return (
            self.max_upload_size_mb
            * 1024
            * 1024
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()