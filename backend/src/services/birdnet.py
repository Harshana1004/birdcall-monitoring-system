from __future__ import annotations

import asyncio
import logging
import os
import threading
from dataclasses import dataclass
from datetime import (
    time,
    timedelta,
)
from pathlib import Path
from typing import Any

from src.core.config import settings
from src.core.exceptions import (
    ProcessingError,
)


# Reduce TensorFlow informational output.
os.environ.setdefault(
    "TF_CPP_MIN_LOG_LEVEL",
    "2",
)


logger = logging.getLogger(
    __name__
)


# ============================================================
# Application-level prediction object
# ============================================================


@dataclass(
    frozen=True,
    slots=True,
)
class BirdNetPrediction:
    """
    Application-level representation of one BirdNET
    prediction.

    The rest of the backend does not need to depend directly
    on BirdNET's own result objects or pandas DataFrames.
    """

    scientific_name: str
    common_name: str

    confidence: float

    start_time_seconds: float
    end_time_seconds: float


# ============================================================
# BirdNET service
# ============================================================


class BirdNetService:
    """
    Adapter around the official BirdNET Python package.

    The acoustic model is loaded lazily and reused for the
    lifetime of the Python process.

    Single-file inference is retained for normal ESP32
    Recording processing.

    Batched inference is used by the Manual Audio Analysis
    feature when multiple ROIs are generated from one source
    recording.
    """

    _model: Any | None = None

    _model_loading_lock = (
        threading.Lock()
    )

    _prediction_lock = (
        threading.Lock()
    )

    # ========================================================
    # Single-file API
    # ========================================================

    async def analyze(
        self,
        audio_path: Path,
    ) -> list[
        BirdNetPrediction
    ]:
        """
        Analyze one ROI audio file.

        This remains the normal inference method for an
        individual ESP32-uploaded Recording.
        """

        resolved_path = (
            Path(
                audio_path
            ).resolve()
        )

        self._validate_audio_path(
            resolved_path
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
                "Unexpected BirdNET failure for "
                "audio file %s.",
                resolved_path,
            )

            raise ProcessingError(
                "BirdNET could not analyze the "
                "audio recording."
            ) from exception

    # ========================================================
    # Batched API
    # ========================================================

    async def analyze_batch(
        self,
        audio_paths: list[
            Path
        ],
    ) -> dict[
        Path,
        list[
            BirdNetPrediction
        ],
    ]:
        """
        Analyze multiple ROI WAV files through one BirdNET
        prediction operation.

        Every supplied input path is included in the returned
        dictionary.

        A file with no predictions above the configured
        confidence threshold maps to an empty list.
        """

        if not audio_paths:
            return {}

        resolved_paths: list[
            Path
        ] = []

        for audio_path in (
            audio_paths
        ):
            resolved_path = (
                Path(
                    audio_path
                ).resolve()
            )

            self._validate_audio_path(
                resolved_path
            )

            resolved_paths.append(
                resolved_path
            )

        try:
            return await asyncio.to_thread(
                self._analyze_batch_synchronously,
                resolved_paths,
            )

        except ProcessingError:
            raise

        except Exception as exception:
            logger.exception(
                "Unexpected BirdNET batched "
                "inference failure."
            )

            raise ProcessingError(
                "BirdNET could not analyze the "
                "audio batch."
            ) from exception

    # ========================================================
    # Single-file synchronous inference
    # ========================================================

    def _analyze_synchronously(
        self,
        audio_path: Path,
    ) -> list[
        BirdNetPrediction
    ]:
        """
        Run one synchronous BirdNET inference call.
        """

        model = (
            self._get_or_load_model()
        )

        try:
            with self._prediction_lock:
                prediction_result = (
                    model.predict(
                        str(
                            audio_path
                        ),

                        top_k=(
                            settings
                            .birdnet_max_predictions_per_interval
                        ),

                        default_confidence_threshold=(
                            settings
                            .birdnet_min_confidence
                        ),
                    )
                )

        except Exception as exception:
            raise ProcessingError(
                "BirdNET inference failed while "
                f"processing '{audio_path.name}'."
            ) from exception

        return (
            self._convert_predictions(
                prediction_result
            )
        )

    # ========================================================
    # Batched synchronous inference
    # ========================================================

    def _analyze_batch_synchronously(
        self,
        audio_paths: list[
            Path
        ],
    ) -> dict[
        Path,
        list[
            BirdNetPrediction
        ],
    ]:
        """
        Run all supplied ROI files through one batched
        BirdNET prediction operation.
        """

        model = (
            self._get_or_load_model()
        )

        try:
            with self._prediction_lock:
                prediction_result = (
                    model.predict(
                        [
                            str(
                                path
                            )
                            for path
                            in audio_paths
                        ],

                        top_k=(
                            settings
                            .birdnet_max_predictions_per_interval
                        ),

                        default_confidence_threshold=(
                            settings
                            .birdnet_min_confidence
                        ),

                        batch_size=(
                            settings
                            .birdnet_batch_size
                        ),

                        n_workers=(
                            settings
                            .birdnet_workers
                        ),

                        n_producers=(
                            settings
                            .birdnet_producers
                        ),

                        prefetch_ratio=(
                            settings
                            .birdnet_prefetch_ratio
                        ),
                    )
                )

        except Exception as exception:
            raise ProcessingError(
                "BirdNET batched inference failed."
            ) from exception

        return (
            self._convert_batch_predictions(
                prediction_result=(
                    prediction_result
                ),
                audio_paths=(
                    audio_paths
                ),
            )
        )

    # ========================================================
    # Model loading
    # ========================================================

    @classmethod
    def _get_or_load_model(
        cls,
    ) -> Any:
        """
        Load one BirdNET acoustic model per Python process.

        Subsequent single and batched predictions reuse the
        same model instance.
        """

        if cls._model is not None:
            return (
                cls._model
            )

        with (
            cls._model_loading_lock
        ):
            if cls._model is not None:
                return (
                    cls._model
                )

            try:
                import birdnet

                logger.info(
                    "Loading BirdNET acoustic model "
                    "version %s with backend %s.",
                    settings
                    .birdnet_model_version,
                    settings
                    .birdnet_backend,
                )

                cls._model = (
                    birdnet.load(
                        "acoustic",
                        settings
                        .birdnet_model_version,
                        settings
                        .birdnet_backend,
                    )
                )

                logger.info(
                    "BirdNET acoustic model loaded "
                    "successfully."
                )

                return (
                    cls._model
                )

            except ImportError as exception:
                raise ProcessingError(
                    "The BirdNET package is not "
                    "installed. Install it using "
                    "'pip install birdnet'."
                ) from exception

            except Exception as exception:
                logger.exception(
                    "BirdNET model loading failed."
                )

                raise ProcessingError(
                    "The BirdNET acoustic model "
                    "could not be loaded."
                ) from exception

    # ========================================================
    # Single-file result conversion
    # ========================================================

    def _convert_predictions(
        self,
        prediction_result: Any,
    ) -> list[
        BirdNetPrediction
    ]:
        """
        Convert a BirdNET result object into application-level
        predictions.
        """

        prediction_frame = (
            self._prediction_result_to_dataframe(
                prediction_result
            )
        )

        if prediction_frame.empty:
            return []

        column_names = (
            self._normalized_column_names(
                prediction_frame
            )
        )

        start_column = (
            self._find_column(
                column_names,
                candidates=(
                    "start_time",
                    "start_time_s",
                    "start",
                ),
                description=(
                    "start time"
                ),
            )
        )

        end_column = (
            self._find_column(
                column_names,
                candidates=(
                    "end_time",
                    "end_time_s",
                    "end",
                ),
                description=(
                    "end time"
                ),
            )
        )

        confidence_column = (
            self._find_column(
                column_names,
                candidates=(
                    "confidence",
                    "probability",
                    "score",
                ),
                description=(
                    "confidence"
                ),
            )
        )

        (
            scientific_name_column,
            common_name_column,
            species_name_column,
        ) = self._find_species_columns(
            column_names
        )

        predictions: list[
            BirdNetPrediction
        ] = []

        for _, row in (
            prediction_frame.iterrows()
        ):
            prediction = (
                self._prediction_from_row(
                    row=row,
                    start_column=(
                        start_column
                    ),
                    end_column=(
                        end_column
                    ),
                    confidence_column=(
                        confidence_column
                    ),
                    scientific_name_column=(
                        scientific_name_column
                    ),
                    common_name_column=(
                        common_name_column
                    ),
                    species_name_column=(
                        species_name_column
                    ),
                )
            )

            if prediction is not None:
                predictions.append(
                    prediction
                )

        return (
            self
            ._limit_predictions_per_interval(
                predictions
            )
        )

    # ========================================================
    # Batched result conversion
    # ========================================================

    def _convert_batch_predictions(
        self,
        *,
        prediction_result: Any,
        audio_paths: list[
            Path
        ],
    ) -> dict[
        Path,
        list[
            BirdNetPrediction
        ],
    ]:
        """
        Convert BirdNET's combined batch DataFrame into
        predictions grouped by input file.
        """

        prediction_frame = (
            self._prediction_result_to_dataframe(
                prediction_result
            )
        )

        predictions_by_path: dict[
            Path,
            list[
                BirdNetPrediction
            ],
        ] = {
            path: []
            for path
            in audio_paths
        }

        if prediction_frame.empty:
            return (
                predictions_by_path
            )

        column_names = (
            self._normalized_column_names(
                prediction_frame
            )
        )

        input_column = (
            self._find_column(
                column_names,
                candidates=(
                    "input",
                    "input_path",
                    "path",
                    "file",
                ),
                description=(
                    "input file"
                ),
            )
        )

        start_column = (
            self._find_column(
                column_names,
                candidates=(
                    "start_time",
                    "start_time_s",
                    "start",
                ),
                description=(
                    "start time"
                ),
            )
        )

        end_column = (
            self._find_column(
                column_names,
                candidates=(
                    "end_time",
                    "end_time_s",
                    "end",
                ),
                description=(
                    "end time"
                ),
            )
        )

        confidence_column = (
            self._find_column(
                column_names,
                candidates=(
                    "confidence",
                    "probability",
                    "score",
                ),
                description=(
                    "confidence"
                ),
            )
        )

        (
            scientific_name_column,
            common_name_column,
            species_name_column,
        ) = self._find_species_columns(
            column_names
        )

        path_lookup = {
            self._normalize_path(
                path
            ): path
            for path
            in audio_paths
        }

        for _, row in (
            prediction_frame.iterrows()
        ):
            normalized_input = (
                self._normalize_path(
                    str(
                        row[
                            input_column
                        ]
                    )
                )
            )

            source_path = (
                path_lookup.get(
                    normalized_input
                )
            )

            if source_path is None:
                logger.warning(
                    "Ignoring BirdNET batch "
                    "prediction for unknown path "
                    "'%s'.",
                    row[
                        input_column
                    ],
                )

                continue

            prediction = (
                self._prediction_from_row(
                    row=row,
                    start_column=(
                        start_column
                    ),
                    end_column=(
                        end_column
                    ),
                    confidence_column=(
                        confidence_column
                    ),
                    scientific_name_column=(
                        scientific_name_column
                    ),
                    common_name_column=(
                        common_name_column
                    ),
                    species_name_column=(
                        species_name_column
                    ),
                )
            )

            if prediction is None:
                continue

            predictions_by_path[
                source_path
            ].append(
                prediction
            )

        for path in (
            audio_paths
        ):
            predictions_by_path[
                path
            ] = (
                self
                ._limit_predictions_per_interval(
                    predictions_by_path[
                        path
                    ]
                )
            )

        return (
            predictions_by_path
        )

    # ========================================================
    # DataFrame helpers
    # ========================================================

    @staticmethod
    def _prediction_result_to_dataframe(
        prediction_result: Any,
    ):
        if not hasattr(
            prediction_result,
            "to_dataframe",
        ):
            raise ProcessingError(
                "BirdNET returned an unsupported "
                "prediction result type: "
                f"{type(prediction_result).__name__}."
            )

        try:
            prediction_frame = (
                prediction_result
                .to_dataframe()
            )

        except Exception as exception:
            raise ProcessingError(
                "BirdNET predictions could not "
                "be converted to a DataFrame."
            ) from exception

        if prediction_frame is None:
            raise ProcessingError(
                "BirdNET returned no prediction "
                "table."
            )

        logger.debug(
            "BirdNET prediction columns: %s",
            list(
                prediction_frame.columns
            ),
        )

        return (
            prediction_frame
        )

    @staticmethod
    def _normalized_column_names(
        prediction_frame,
    ) -> dict[
        str,
        Any,
    ]:
        return {
            str(
                column
            )
            .strip()
            .lower():
            column

            for column
            in prediction_frame.columns
        }

    def _find_species_columns(
        self,
        column_names: dict[
            str,
            Any,
        ],
    ) -> tuple[
        Any | None,
        Any | None,
        Any | None,
    ]:
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
            and scientific_name_column
            is None
        ):
            raise ProcessingError(
                "BirdNET returned an unexpected "
                "result format. No species-name "
                "column was found. Available "
                "columns: "
                f"{list(column_names.values())}."
            )

        return (
            scientific_name_column,
            common_name_column,
            species_name_column,
        )

    # ========================================================
    # Row conversion
    # ========================================================

    def _prediction_from_row(
        self,
        *,
        row,
        start_column: Any,
        end_column: Any,
        confidence_column: Any,
        scientific_name_column: Any | None,
        common_name_column: Any | None,
        species_name_column: Any | None,
    ) -> BirdNetPrediction | None:
        confidence = float(
            row[
                confidence_column
            ]
        )

        if (
            confidence
            < settings
            .birdnet_min_confidence
        ):
            return None

        if (
            scientific_name_column
            is not None
        ):
            scientific_name = str(
                row[
                    scientific_name_column
                ]
            ).strip()

            if (
                common_name_column
                is not None
            ):
                common_name = str(
                    row[
                        common_name_column
                    ]
                ).strip()

            else:
                common_name = (
                    scientific_name
                )

        else:
            species_name = str(
                row[
                    species_name_column
                ]
            ).strip()

            (
                scientific_name,
                common_name,
            ) = (
                self._split_species_name(
                    species_name
                )
            )

        if not scientific_name:
            logger.warning(
                "Ignoring BirdNET prediction "
                "with empty scientific name."
            )

            return None

        if not common_name:
            common_name = (
                scientific_name
            )

        start_time_seconds = (
            self._time_value_to_seconds(
                row[
                    start_column
                ]
            )
        )

        end_time_seconds = (
            self._time_value_to_seconds(
                row[
                    end_column
                ]
            )
        )

        if (
            end_time_seconds
            <= start_time_seconds
        ):
            logger.warning(
                "Ignoring BirdNET prediction "
                "with invalid interval: "
                "start=%s, end=%s, species=%s.",
                start_time_seconds,
                end_time_seconds,
                scientific_name,
            )

            return None

        return BirdNetPrediction(
            scientific_name=(
                scientific_name
            ),

            common_name=(
                common_name
            ),

            confidence=(
                confidence
            ),

            start_time_seconds=(
                start_time_seconds
            ),

            end_time_seconds=(
                end_time_seconds
            ),
        )

    # ========================================================
    # General helpers
    # ========================================================

    @staticmethod
    def _validate_audio_path(
        audio_path: Path,
    ) -> None:
        if not audio_path.exists():
            raise ProcessingError(
                f"Audio file '{audio_path}' "
                "does not exist."
            )

        if not audio_path.is_file():
            raise ProcessingError(
                f"Audio path '{audio_path}' "
                "is not a file."
            )

    @staticmethod
    def _normalize_path(
        value: str | Path,
    ) -> str:
        """
        Normalize paths for reliable comparison on Windows.
        """

        return os.path.normcase(
            os.path.normpath(
                str(
                    Path(
                        value
                    ).resolve()
                )
            )
        )

    @staticmethod
    def _find_column(
        column_names: dict[
            str,
            Any,
        ],
        *,
        candidates: tuple[
            str,
            ...
        ],
        description: str,
    ) -> Any:
        for candidate in (
            candidates
        ):
            if (
                candidate
                in column_names
            ):
                return (
                    column_names[
                        candidate
                    ]
                )

        raise ProcessingError(
            "BirdNET returned an unexpected "
            "result format. "
            f"No {description} column was "
            "found. Available columns: "
            f"{list(column_names.values())}."
        )

    @staticmethod
    def _find_optional_column(
        column_names: dict[
            str,
            Any,
        ],
        *,
        candidates: tuple[
            str,
            ...
        ],
    ) -> Any | None:
        for candidate in (
            candidates
        ):
            if (
                candidate
                in column_names
            ):
                return (
                    column_names[
                        candidate
                    ]
                )

        return None

    @staticmethod
    def _split_species_name(
        species_name: str,
    ) -> tuple[
        str,
        str,
    ]:
        """
        Split labels such as:

            Todiramphus chloris_Collared Kingfisher
        """

        if "_" not in species_name:
            return (
                species_name,
                species_name,
            )

        (
            scientific_name,
            common_name,
        ) = (
            species_name.split(
                "_",
                maxsplit=1,
            )
        )

        scientific_name = (
            scientific_name.strip()
        )

        common_name = (
            common_name.strip()
        )

        if not scientific_name:
            scientific_name = (
                species_name
            )

        if not common_name:
            common_name = (
                scientific_name
            )

        return (
            scientific_name,
            common_name,
        )

    @classmethod
    def _time_value_to_seconds(
        cls,
        value: Any,
    ) -> float:
        """
        Convert BirdNET/pandas timestamp values into seconds.
        """

        if isinstance(
            value,
            timedelta,
        ):
            return float(
                value.total_seconds()
            )

        if isinstance(
            value,
            time,
        ):
            return float(
                value.hour
                * 3600
                + value.minute
                * 60
                + value.second
                + value.microsecond
                / 1_000_000
            )

        if isinstance(
            value,
            (
                int,
                float,
            ),
        ):
            return float(
                value
            )

        if hasattr(
            value,
            "total_seconds",
        ):
            try:
                return float(
                    value.total_seconds()
                )

            except Exception as exception:
                raise ProcessingError(
                    "BirdNET returned an invalid "
                    "time value."
                ) from exception

        normalized_value = str(
            value
        ).strip()

        if not normalized_value:
            raise ProcessingError(
                "BirdNET returned an empty "
                "timestamp."
            )

        try:
            return float(
                normalized_value
            )

        except ValueError:
            pass

        parts = (
            normalized_value.split(
                ":"
            )
        )

        if len(
            parts
        ) != 3:
            raise ProcessingError(
                "BirdNET returned an unsupported "
                "timestamp value: "
                f"'{normalized_value}'."
            )

        try:
            hours = float(
                parts[0]
            )

            minutes = float(
                parts[1]
            )

            seconds = float(
                parts[2]
            )

        except ValueError as exception:
            raise ProcessingError(
                "BirdNET returned an invalid "
                "timestamp value: "
                f"'{normalized_value}'."
            ) from exception

        return float(
            hours
            * 3600
            + minutes
            * 60
            + seconds
        )

    @staticmethod
    def _limit_predictions_per_interval(
        predictions: list[
            BirdNetPrediction
        ],
    ) -> list[
        BirdNetPrediction
    ]:
        """
        Keep only the strongest configured predictions for
        each BirdNET analysis interval.
        """

        predictions_by_interval: dict[
            tuple[
                float,
                float,
            ],
            list[
                BirdNetPrediction
            ],
        ] = {}

        for prediction in (
            predictions
        ):
            interval = (
                prediction
                .start_time_seconds,
                prediction
                .end_time_seconds,
            )

            predictions_by_interval.setdefault(
                interval,
                [],
            ).append(
                prediction
            )

        limited_predictions: list[
            BirdNetPrediction
        ] = []

        for interval_predictions in (
            predictions_by_interval.values()
        ):
            strongest_predictions = (
                sorted(
                    interval_predictions,
                    key=lambda prediction: (
                        prediction.confidence
                    ),
                    reverse=True,
                )[
                    :
                    settings
                    .birdnet_max_predictions_per_interval
                ]
            )

            limited_predictions.extend(
                strongest_predictions
            )

        return sorted(
            limited_predictions,
            key=lambda prediction: (
                prediction
                .start_time_seconds,
                -prediction.confidence,
            ),
        )