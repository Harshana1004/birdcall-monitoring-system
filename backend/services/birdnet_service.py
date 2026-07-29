import asyncio
import logging
import os
import threading
from dataclasses import dataclass
from datetime import time, timedelta
from pathlib import Path
from typing import Any

from core.config import settings
from core.exceptions import ProcessingError


os.environ.setdefault(
    "TF_CPP_MIN_LOG_LEVEL",
    "2",
)


logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class BirdNetPrediction:
    """
    Application-level representation of one BirdNET prediction.

    This prevents the rest of the backend from depending directly
    on BirdNET's internal result objects or pandas DataFrames.
    """

    scientific_name: str
    common_name: str
    confidence: float
    start_time_seconds: float
    end_time_seconds: float


class BirdNetService:
    """
    Adapter around the official BirdNET Python package.

    The BirdNET model is loaded lazily and reused for the lifetime
    of the Python process.

    Model loading and inference are protected by locks because the
    underlying model should not be assumed to support simultaneous
    calls from multiple threads.
    """

    _model: Any | None = None

    _model_loading_lock = threading.Lock()
    _prediction_lock = threading.Lock()

    async def analyze(
        self,
        audio_path: Path,
    ) -> list[BirdNetPrediction]:
        """
        Analyze one ROI audio file.

        BirdNET inference is synchronous and CPU-bound, so it runs
        in a worker thread rather than blocking FastAPI's event loop.
        """

        resolved_path = audio_path.resolve()

        if not resolved_path.exists():
            raise ProcessingError(
                f"Audio file '{resolved_path}' does not exist."
            )

        if not resolved_path.is_file():
            raise ProcessingError(
                f"Audio path '{resolved_path}' is not a file."
            )

        try:
            return await asyncio.to_thread(
                self._analyze_synchronously,
                resolved_path,
            )

        except ProcessingError:
            raise

        except Exception as exception:
            logger.exception(
                "Unexpected BirdNET failure for audio file %s.",
                resolved_path,
            )

            raise ProcessingError(
                "BirdNET could not analyze the audio recording."
            ) from exception

    def _analyze_synchronously(
        self,
        audio_path: Path,
    ) -> list[BirdNetPrediction]:
        """
        Run BirdNET inference synchronously in a worker thread.
        """

        model = self._get_or_load_model()

        try:
            with self._prediction_lock:
                prediction_result = model.predict(
                    str(audio_path),
                    top_k=(
                        settings
                        .birdnet_max_predictions_per_interval
                    ),
                    default_confidence_threshold=(
                        settings.birdnet_min_confidence
                    ),
                )

        except Exception as exception:
            raise ProcessingError(
                "BirdNET inference failed while processing "
                f"'{audio_path.name}'."
            ) from exception

        return self._convert_predictions(
            prediction_result
        )

    @classmethod
    def _get_or_load_model(
        cls,
    ) -> Any:
        """
        Load and cache one BirdNET model per Python process.

        In a future worker deployment, each worker process will load
        and reuse its own BirdNET model instance.
        """

        if cls._model is not None:
            return cls._model

        with cls._model_loading_lock:
            if cls._model is not None:
                return cls._model

            try:
                import birdnet

                logger.info(
                    "Loading BirdNET acoustic model version %s "
                    "with backend %s.",
                    settings.birdnet_model_version,
                    settings.birdnet_backend,
                )

                cls._model = birdnet.load(
                    "acoustic",
                    settings.birdnet_model_version,
                    settings.birdnet_backend,
                )

                logger.info(
                    "BirdNET acoustic model loaded successfully."
                )

                return cls._model

            except ImportError as exception:
                raise ProcessingError(
                    "The BirdNET package is not installed. "
                    "Install it using 'pip install birdnet'."
                ) from exception

            except Exception as exception:
                logger.exception(
                    "BirdNET model loading failed."
                )

                raise ProcessingError(
                    "The BirdNET acoustic model could not be loaded."
                ) from exception

    def _convert_predictions(
        self,
        prediction_result: Any,
    ) -> list[BirdNetPrediction]:
        """
        Convert BirdNET's AcousticFilePredictionResult into
        application-level BirdNetPrediction objects.
        """

        if not hasattr(
            prediction_result,
            "to_dataframe",
        ):
            raise ProcessingError(
                "BirdNET returned an unsupported prediction "
                f"result type: "
                f"{type(prediction_result).__name__}."
            )

        try:
            prediction_frame = (
                prediction_result.to_dataframe()
            )

        except Exception as exception:
            raise ProcessingError(
                "BirdNET predictions could not be converted "
                "to a DataFrame."
            ) from exception

        if prediction_frame is None:
            raise ProcessingError(
                "BirdNET returned no prediction table."
            )

        if prediction_frame.empty:
            return []

        logger.debug(
            "BirdNET prediction columns: %s",
            list(prediction_frame.columns),
        )

        column_names = {
            str(column).strip().lower(): column
            for column in prediction_frame.columns
        }

        start_column = self._find_column(
            column_names,
            candidates=(
                "start_time",
                "start_time_s",
                "start",
            ),
            description="start time",
        )

        end_column = self._find_column(
            column_names,
            candidates=(
                "end_time",
                "end_time_s",
                "end",
            ),
            description="end time",
        )

        confidence_column = self._find_column(
            column_names,
            candidates=(
                "confidence",
                "probability",
                "score",
            ),
            description="confidence",
        )

        scientific_name_column = (
            self._find_optional_column(
                column_names,
                candidates=(
                    "scientific_name",
                    "scientific name",
                ),
            )
        )

        common_name_column = (
            self._find_optional_column(
                column_names,
                candidates=(
                    "common_name",
                    "common name",
                ),
            )
        )

        species_name_column = (
            self._find_optional_column(
                column_names,
                candidates=(
                    "species_name",
                    "species",
                    "label",
                ),
            )
        )

        if (
            species_name_column is None
            and scientific_name_column is None
        ):
            raise ProcessingError(
                "BirdNET returned an unexpected result format. "
                "No species-name column was found. Available "
                f"columns: {list(prediction_frame.columns)}."
            )

        predictions: list[BirdNetPrediction] = []

        for _, row in prediction_frame.iterrows():
            confidence = float(
                row[confidence_column]
            )

            if confidence < settings.birdnet_min_confidence:
                continue

            if scientific_name_column is not None:
                scientific_name = str(
                    row[scientific_name_column]
                ).strip()

                if common_name_column is not None:
                    common_name = str(
                        row[common_name_column]
                    ).strip()
                else:
                    common_name = scientific_name

            else:
                species_name = str(
                    row[species_name_column]
                ).strip()

                scientific_name, common_name = (
                    self._split_species_name(
                        species_name
                    )
                )

            if not scientific_name:
                logger.warning(
                    "Ignoring BirdNET prediction with an "
                    "empty scientific name."
                )
                continue

            if not common_name:
                common_name = scientific_name

            start_time_seconds = (
                self._time_value_to_seconds(
                    row[start_column]
                )
            )

            end_time_seconds = (
                self._time_value_to_seconds(
                    row[end_column]
                )
            )

            if end_time_seconds <= start_time_seconds:
                logger.warning(
                    "Ignoring BirdNET prediction with invalid "
                    "interval: start=%s, end=%s, species=%s.",
                    start_time_seconds,
                    end_time_seconds,
                    scientific_name,
                )
                continue

            predictions.append(
                BirdNetPrediction(
                    scientific_name=scientific_name,
                    common_name=common_name,
                    confidence=confidence,
                    start_time_seconds=(
                        start_time_seconds
                    ),
                    end_time_seconds=(
                        end_time_seconds
                    ),
                )
            )

        return self._limit_predictions_per_interval(
            predictions
        )

    @staticmethod
    def _find_column(
        column_names: dict[str, Any],
        *,
        candidates: tuple[str, ...],
        description: str,
    ) -> Any:
        """
        Find a required DataFrame column.

        Several possible names are supported to tolerate small
        BirdNET output-format changes between versions.
        """

        for candidate in candidates:
            if candidate in column_names:
                return column_names[candidate]

        raise ProcessingError(
            "BirdNET returned an unexpected result format. "
            f"No {description} column was found. Available "
            f"columns: {list(column_names.values())}."
        )

    @staticmethod
    def _find_optional_column(
        column_names: dict[str, Any],
        *,
        candidates: tuple[str, ...],
    ) -> Any | None:
        """Find an optional DataFrame column."""

        for candidate in candidates:
            if candidate in column_names:
                return column_names[candidate]

        return None

    @staticmethod
    def _split_species_name(
        species_name: str,
    ) -> tuple[str, str]:
        """
        Split BirdNET's combined species label.

        BirdNET commonly returns labels in this form:

            Scientific name_Common name
        """

        if "_" not in species_name:
            return species_name, species_name

        scientific_name, common_name = (
            species_name.split(
                "_",
                maxsplit=1,
            )
        )

        scientific_name = scientific_name.strip()
        common_name = common_name.strip()

        if not scientific_name:
            scientific_name = species_name

        if not common_name:
            common_name = scientific_name

        return scientific_name, common_name

    @classmethod
    def _time_value_to_seconds(
        cls,
        value: Any,
    ) -> float:
        """
        Convert a BirdNET or pandas time value into seconds.

        Supported values include:

        - pandas.Timedelta
        - datetime.timedelta
        - datetime.time
        - numeric seconds
        - strings such as 00:00:03.500
        """

        if isinstance(value, timedelta):
            return float(
                value.total_seconds()
            )

        if isinstance(value, time):
            return float(
                value.hour * 3600
                + value.minute * 60
                + value.second
                + value.microsecond / 1_000_000
            )

        if isinstance(value, (int, float)):
            return float(value)

        if hasattr(value, "total_seconds"):
            try:
                return float(
                    value.total_seconds()
                )

            except Exception as exception:
                raise ProcessingError(
                    "BirdNET returned an invalid time value."
                ) from exception

        normalized_value = str(value).strip()

        if not normalized_value:
            raise ProcessingError(
                "BirdNET returned an empty timestamp."
            )

        try:
            return float(normalized_value)

        except ValueError:
            pass

        parts = normalized_value.split(":")

        if len(parts) != 3:
            raise ProcessingError(
                "BirdNET returned an unsupported timestamp "
                f"value: '{normalized_value}'."
            )

        try:
            hours = float(parts[0])
            minutes = float(parts[1])
            seconds = float(parts[2])

        except ValueError as exception:
            raise ProcessingError(
                "BirdNET returned an invalid timestamp "
                f"value: '{normalized_value}'."
            ) from exception

        return float(
            hours * 3600
            + minutes * 60
            + seconds
        )

    @staticmethod
    def _limit_predictions_per_interval(
        predictions: list[BirdNetPrediction],
    ) -> list[BirdNetPrediction]:
        """
        Keep only the strongest configured predictions for each
        BirdNET time interval.
        """

        predictions_by_interval: dict[
            tuple[float, float],
            list[BirdNetPrediction],
        ] = {}

        for prediction in predictions:
            interval = (
                prediction.start_time_seconds,
                prediction.end_time_seconds,
            )

            predictions_by_interval.setdefault(
                interval,
                [],
            ).append(prediction)

        limited_predictions: list[
            BirdNetPrediction
        ] = []

        for interval_predictions in (
            predictions_by_interval.values()
        ):
            strongest_predictions = sorted(
                interval_predictions,
                key=lambda prediction: (
                    prediction.confidence
                ),
                reverse=True,
            )[
                :settings
                .birdnet_max_predictions_per_interval
            ]

            limited_predictions.extend(
                strongest_predictions
            )

        return sorted(
            limited_predictions,
            key=lambda prediction: (
                prediction.start_time_seconds,
                -prediction.confidence,
            ),
        )