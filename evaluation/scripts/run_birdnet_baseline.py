from __future__ import annotations

import argparse
import csv
import os
import time
from collections import defaultdict
from pathlib import Path

# Reduce TensorFlow informational logging.
os.environ.setdefault(
    "TF_CPP_MIN_LOG_LEVEL",
    "2",
)

import birdnet
import matplotlib.pyplot as plt
import pandas as pd

from sklearn.metrics import (
    ConfusionMatrixDisplay,
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)


# ============================================================
# Paths
# ============================================================

PROJECT_ROOT = Path(
    __file__
).resolve().parents[2]

DATASET_ROOT = (
    PROJECT_ROOT
    / "evaluation"
    / "data"
    / "mygardenbird"
    / "raw"
)

PREDICTIONS_DIRECTORY = (
    PROJECT_ROOT
    / "evaluation"
    / "predictions"
)

RESULTS_DIRECTORY = (
    PROJECT_ROOT
    / "evaluation"
    / "results"
)

PLOTS_DIRECTORY = (
    PROJECT_ROOT
    / "evaluation"
    / "plots"
)


# ============================================================
# Experiment configuration
# ============================================================

EXPERIMENT_ID = "E0"

MODEL_VERSION = "2.4"
MODEL_BACKEND = "tf"

CONFIDENCE_THRESHOLD = 0.25
TOP_K = 5

DEFAULT_BATCH_SIZE = 16
DEFAULT_N_WORKERS = 2
DEFAULT_N_PRODUCERS = 2
DEFAULT_PREFETCH_RATIO = 2

CLIP_DURATION_SECONDS = 3.0

ABSTAIN_LABEL = "__ABSTAIN__"
OTHER_LABEL = "__OTHER__"


# ============================================================
# Command-line arguments
# ============================================================


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the E0 BirdNET 2.4 baseline experiment "
            "on the MyGardenBird dataset using batched inference."
        )
    )

    parser.add_argument(
        "--limit-per-species",
        type=int,
        default=None,
        help=(
            "Maximum number of clips evaluated per species. "
            "If omitted, all available clips are evaluated."
        ),
    )

    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help="BirdNET inference batch size.",
    )

    parser.add_argument(
        "--workers",
        type=int,
        default=DEFAULT_N_WORKERS,
        help="Number of BirdNET inference workers.",
    )

    parser.add_argument(
        "--producers",
        type=int,
        default=DEFAULT_N_PRODUCERS,
        help="Number of BirdNET audio producer workers.",
    )

    return parser.parse_args()


# ============================================================
# Dataset
# ============================================================


def discover_dataset() -> dict[str, list[Path]]:
    """
    Discover MyGardenBird WAV files.

    Directory names are treated as the ground-truth
    common species names.
    """

    if not DATASET_ROOT.exists():
        raise FileNotFoundError(
            "MyGardenBird dataset directory was not found at "
            f"'{DATASET_ROOT}'."
        )

    species_files: dict[
        str,
        list[Path],
    ] = {}

    for species_directory in sorted(
        DATASET_ROOT.iterdir()
    ):
        if not species_directory.is_dir():
            continue

        wav_files = sorted(
            path.resolve()
            for path in species_directory.glob(
                "*.wav"
            )
            if path.is_file()
        )

        if wav_files:
            species_files[
                species_directory.name
            ] = wav_files

    if not species_files:
        raise RuntimeError(
            "No species folders containing WAV files "
            f"were found inside '{DATASET_ROOT}'."
        )

    return species_files


def select_audio_files(
    *,
    species_files: dict[str, list[Path]],
    limit_per_species: int | None,
) -> tuple[
    list[Path],
    dict[str, str],
]:
    """
    Select audio clips for the current experiment.

    Returns:
        selected_audio_files:
            Flat ordered input list.

        true_species_by_path:
            Mapping from normalized absolute path to
            ground-truth species.
    """

    selected_audio_files: list[
        Path
    ] = []

    true_species_by_path: dict[
        str,
        str,
    ] = {}

    for species, files in sorted(
        species_files.items()
    ):
        if limit_per_species is None:
            selected_files = files
        else:
            selected_files = files[
                :limit_per_species
            ]

        for audio_path in selected_files:
            resolved_path = (
                audio_path.resolve()
            )

            selected_audio_files.append(
                resolved_path
            )

            true_species_by_path[
                normalize_path(
                    resolved_path
                )
            ] = species

    return (
        selected_audio_files,
        true_species_by_path,
    )


# ============================================================
# Normalization helpers
# ============================================================


def normalize_path(
    value: str | Path,
) -> str:
    """
    Normalize a path for reliable comparison on Windows.
    """

    return os.path.normcase(
        os.path.normpath(
            str(
                Path(value).resolve()
            )
        )
    )


def normalize_species_name(
    value: str,
) -> str:
    """
    Normalize common species names for comparison.
    """

    return " ".join(
        value.strip()
        .lower()
        .replace("-", " ")
        .replace("_", " ")
        .split()
    )


def split_species_name(
    combined_name: str,
) -> tuple[str, str]:
    """
    Split BirdNET labels such as:

        Todiramphus chloris_Collared Kingfisher
    """

    value = combined_name.strip()

    if "_" not in value:
        return value, value

    scientific_name, common_name = (
        value.split(
            "_",
            maxsplit=1,
        )
    )

    return (
        scientific_name.strip(),
        common_name.strip(),
    )


def map_prediction_to_dataset_class(
    *,
    common_name: str,
    scientific_name: str,
    species_names: list[str],
) -> str:
    """
    Map a BirdNET prediction to one of the MyGardenBird
    dataset classes.

    Scientific-name and common-name aliases are supported
    where the dataset taxonomy/name differs from BirdNET.
    """

    normalized_common_name = (
        normalize_species_name(
            common_name
        )
    )

    normalized_scientific_name = (
        scientific_name
        .strip()
        .lower()
    )

    # --------------------------------------------------------
    # Explicit taxonomy / naming aliases
    # --------------------------------------------------------

    species_aliases = {
        "Pied Fantail": {
            "common_names": {
                "pied fantail",
                "malaysian pied fantail",
            },
            "scientific_names": {
                "rhipidura javanica",
            },
        },
    }

    # First check explicit aliases.
    for dataset_species, aliases in (
        species_aliases.items()
    ):
        normalized_alias_common_names = {
            normalize_species_name(
                alias
            )
            for alias in aliases[
                "common_names"
            ]
        }

        normalized_alias_scientific_names = {
            alias.strip().lower()
            for alias in aliases[
                "scientific_names"
            ]
        }

        if (
            normalized_common_name
            in normalized_alias_common_names
            or normalized_scientific_name
            in normalized_alias_scientific_names
        ):
            return dataset_species

    # --------------------------------------------------------
    # Standard exact common-name matching
    # --------------------------------------------------------

    for species in species_names:
        if (
            normalize_species_name(
                species
            )
            == normalized_common_name
        ):
            return species

    return OTHER_LABEL


# ============================================================
# BirdNET result parsing
# ============================================================


def parse_prediction_dataframe(
    prediction_frame: pd.DataFrame,
) -> dict[
    str,
    list[dict[str, object]],
]:
    """
    Convert BirdNET's combined batched DataFrame into
    predictions grouped by input file.

    Expected columns from BirdNET 0.2.16:

        input
        start_time
        end_time
        species_name
        confidence
    """

    required_columns = {
        "input",
        "species_name",
        "confidence",
    }

    missing_columns = (
        required_columns
        - set(
            prediction_frame.columns
        )
    )

    if missing_columns:
        raise RuntimeError(
            "BirdNET returned an unexpected DataFrame. "
            "Missing columns: "
            f"{sorted(missing_columns)}. "
            "Available columns: "
            f"{list(prediction_frame.columns)}"
        )

    predictions_by_path: dict[
        str,
        list[dict[str, object]],
    ] = defaultdict(list)

    for _, row in prediction_frame.iterrows():
        input_path = normalize_path(
            str(row["input"])
        )

        scientific_name, common_name = (
            split_species_name(
                str(
                    row[
                        "species_name"
                    ]
                )
            )
        )

        prediction = {
            "scientific_name": scientific_name,
            "common_name": common_name,
            "confidence": float(
                row["confidence"]
            ),
            "start_time": float(
                row.get(
                    "start_time",
                    0.0,
                )
            ),
            "end_time": float(
                row.get(
                    "end_time",
                    CLIP_DURATION_SECONDS,
                )
            ),
        }

        predictions_by_path[
            input_path
        ].append(
            prediction
        )

    for input_path in (
        predictions_by_path
    ):
        predictions_by_path[
            input_path
        ].sort(
            key=lambda prediction: (
                float(
                    prediction[
                        "confidence"
                    ]
                )
            ),
            reverse=True,
        )

    return dict(
        predictions_by_path
    )


# ============================================================
# Output helpers
# ============================================================


def save_confusion_matrix(
    *,
    true_labels: list[str],
    predicted_labels: list[str],
    species_names: list[str],
    suffix: str,
) -> Path:
    """
    Save a confusion matrix including OTHER and ABSTAIN.
    """

    labels = [
        *species_names,
        OTHER_LABEL,
        ABSTAIN_LABEL,
    ]

    matrix = confusion_matrix(
        true_labels,
        predicted_labels,
        labels=labels,
    )

    figure, axis = plt.subplots(
        figsize=(16, 14)
    )

    display = ConfusionMatrixDisplay(
        confusion_matrix=matrix,
        display_labels=labels,
    )

    display.plot(
        ax=axis,
        xticks_rotation=45,
        values_format="d",
        colorbar=False,
    )

    axis.set_title(
        "E0 BirdNET 2.4 Baseline — MyGardenBird"
    )

    figure.tight_layout()

    output_path = (
        PLOTS_DIRECTORY
        / f"e0_confusion_matrix{suffix}.png"
    )

    figure.savefig(
        output_path,
        dpi=200,
        bbox_inches="tight",
    )

    plt.close(
        figure
    )

    return output_path


def save_species_f1_chart(
    *,
    species_metric_rows: list[
        dict[str, object]
    ],
    suffix: str,
) -> Path:
    """
    Produce a simple per-species F1 chart.
    """

    species = [
        str(row["species"])
        for row in species_metric_rows
    ]

    f1_values = [
        float(row["f1_score"])
        for row in species_metric_rows
    ]

    figure, axis = plt.subplots(
        figsize=(12, 7)
    )

    axis.barh(
        species,
        f1_values,
    )

    axis.set_xlim(
        0.0,
        1.0,
    )

    axis.set_xlabel(
        "F1-score"
    )

    axis.set_ylabel(
        "Species"
    )

    axis.set_title(
        "E0 BirdNET 2.4 Per-Species F1"
    )

    figure.tight_layout()

    output_path = (
        PLOTS_DIRECTORY
        / f"e0_species_f1{suffix}.png"
    )

    figure.savefig(
        output_path,
        dpi=200,
        bbox_inches="tight",
    )

    plt.close(
        figure
    )

    return output_path


# ============================================================
# Main experiment
# ============================================================


def main() -> None:
    arguments = parse_arguments()

    if (
        arguments.limit_per_species
        is not None
        and arguments.limit_per_species <= 0
    ):
        raise ValueError(
            "--limit-per-species must be greater than zero."
        )

    if arguments.batch_size <= 0:
        raise ValueError(
            "--batch-size must be greater than zero."
        )

    if arguments.workers <= 0:
        raise ValueError(
            "--workers must be greater than zero."
        )

    if arguments.producers <= 0:
        raise ValueError(
            "--producers must be greater than zero."
        )

    PREDICTIONS_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True,
    )

    RESULTS_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True,
    )

    PLOTS_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True,
    )

    species_files = discover_dataset()

    species_names = sorted(
        species_files.keys()
    )

    (
        selected_audio_files,
        true_species_by_path,
    ) = select_audio_files(
        species_files=species_files,
        limit_per_species=(
            arguments.limit_per_species
        ),
    )

    total_clips = len(
        selected_audio_files
    )

    if total_clips == 0:
        raise RuntimeError(
            "No audio files were selected."
        )

    # Use unique filenames so pilot results do not
    # overwrite full experiment outputs.

    if arguments.limit_per_species is None:
        suffix = "_full"
        run_name = "FULL"
    else:
        suffix = (
            f"_n{arguments.limit_per_species}"
        )
        run_name = (
            f"{arguments.limit_per_species} "
            "clips/species"
        )

    print()
    print(
        "E0 BirdNET 2.4 Baseline Evaluation"
    )
    print(
        "=" * 60
    )

    print(
        f"Run: {run_name}"
    )

    print(
        f"Species: "
        f"{len(species_names)}"
    )

    print(
        f"Clips: "
        f"{total_clips}"
    )

    print(
        f"Confidence threshold: "
        f"{CONFIDENCE_THRESHOLD}"
    )

    print(
        f"Top-K: "
        f"{TOP_K}"
    )

    print(
        f"Batch size: "
        f"{arguments.batch_size}"
    )

    print(
        f"Workers: "
        f"{arguments.workers}"
    )

    print(
        f"Producers: "
        f"{arguments.producers}"
    )

    print()
    print(
        "Loading BirdNET model..."
    )

    model_load_start = (
        time.perf_counter()
    )

    model = birdnet.load(
        "acoustic",
        MODEL_VERSION,
        MODEL_BACKEND,
    )

    model_load_seconds = (
        time.perf_counter()
        - model_load_start
    )

    print(
        f"Model loaded in "
        f"{model_load_seconds:.3f} s"
    )

    print()
    print(
        "Running batched inference..."
    )

    inference_start = (
        time.perf_counter()
    )

    prediction_result = model.predict(
        [
            str(path)
            for path in selected_audio_files
        ],
        top_k=TOP_K,
        default_confidence_threshold=(
            CONFIDENCE_THRESHOLD
        ),
        batch_size=(
            arguments.batch_size
        ),
        n_workers=(
            arguments.workers
        ),
        n_producers=(
            arguments.producers
        ),
        prefetch_ratio=(
            DEFAULT_PREFETCH_RATIO
        ),
        show_stats="minimal",
    )

    total_inference_seconds = (
        time.perf_counter()
        - inference_start
    )

    prediction_frame = (
        prediction_result.to_dataframe()
    )

    if prediction_frame is None:
        raise RuntimeError(
            "BirdNET returned no DataFrame."
        )

    predictions_by_path = (
        parse_prediction_dataframe(
            prediction_frame
        )
    )

    print()
    print(
        "Calculating classification metrics..."
    )

    true_labels: list[str] = []
    predicted_labels: list[str] = []

    clip_rows: list[
        dict[str, object]
    ] = []

    prediction_rows: list[
        dict[str, object]
    ] = []

    top3_correct = 0
    top5_correct = 0

    abstention_count = 0
    outside_dataset_count = 0

    correct_top1_count = 0

    confidence_values: list[
        float
    ] = []

    for audio_path in (
        selected_audio_files
    ):
        normalized_path = (
            normalize_path(
                audio_path
            )
        )

        true_species = (
            true_species_by_path[
                normalized_path
            ]
        )

        predictions = (
            predictions_by_path.get(
                normalized_path,
                [],
            )
        )

        true_labels.append(
            true_species
        )

        if predictions:
            top_prediction = (
                predictions[0]
            )

            predicted_common_name = str(
                top_prediction[
                    "common_name"
                ]
            )

            predicted_scientific_name = str(
                top_prediction[
                    "scientific_name"
                ]
            )

            confidence = float(
                top_prediction[
                    "confidence"
                ]
            )

            confidence_values.append(
                confidence
            )

            mapped_prediction = (
                map_prediction_to_dataset_class(
                    common_name=(
                        predicted_common_name
                    ),
                    scientific_name=(
                        predicted_scientific_name
                    ),
                    species_names=(
                        species_names
                    ),
                )
            )

            if (
                mapped_prediction
                == OTHER_LABEL
            ):
                outside_dataset_count += 1

        else:
            predicted_common_name = ""
            predicted_scientific_name = ""
            confidence = 0.0
            mapped_prediction = (
                ABSTAIN_LABEL
            )

            abstention_count += 1

        predicted_labels.append(
            mapped_prediction
        )

        top1_correct = (
            mapped_prediction
            == true_species
        )

        if top1_correct:
            correct_top1_count += 1

        # --------------------------------------------------------
        # Top-K evaluation
        # --------------------------------------------------------

        mapped_ranked_predictions = [
            map_prediction_to_dataset_class(
                common_name=str(
                    prediction[
                        "common_name"
                    ]
                ),
                scientific_name=str(
                    prediction[
                        "scientific_name"
                    ]
                ),
                species_names=(
                    species_names
                ),
            )
            for prediction
            in predictions
        ]

        if (
            true_species
            in mapped_ranked_predictions[:3]
        ):
            top3_correct += 1

        if (
            true_species
            in mapped_ranked_predictions[:5]
        ):
            top5_correct += 1
        clip_rows.append(
            {
                "file_name": (
                    audio_path.name
                ),
                "input_path": (
                    str(audio_path)
                ),
                "true_species": (
                    true_species
                ),
                "predicted_scientific_name": (
                    predicted_scientific_name
                ),
                "predicted_common_name": (
                    predicted_common_name
                ),
                "mapped_prediction": (
                    mapped_prediction
                ),
                "confidence": confidence,
                "correct_top1": (
                    top1_correct
                ),
                "prediction_count": (
                    len(predictions)
                ),
            }
        )

        for rank, prediction in enumerate(
            predictions,
            start=1,
        ):
            prediction_rows.append(
                {
                    "file_name": (
                        audio_path.name
                    ),
                    "input_path": (
                        str(audio_path)
                    ),
                    "true_species": (
                        true_species
                    ),
                    "rank": rank,
                    "scientific_name": (
                        prediction[
                            "scientific_name"
                        ]
                    ),
                    "common_name": (
                        prediction[
                            "common_name"
                        ]
                    ),
                    "confidence": (
                        prediction[
                            "confidence"
                        ]
                    ),
                    "start_time": (
                        prediction[
                            "start_time"
                        ]
                    ),
                    "end_time": (
                        prediction[
                            "end_time"
                        ]
                    ),
                }
            )

    # ========================================================
    # Overall metrics
    # ========================================================

    top1_accuracy = accuracy_score(
        true_labels,
        predicted_labels,
    )

    top3_accuracy = (
        top3_correct
        / total_clips
    )

    top5_accuracy = (
        top5_correct
        / total_clips
    )

    macro_precision = precision_score(
        true_labels,
        predicted_labels,
        labels=species_names,
        average="macro",
        zero_division=0,
    )

    macro_recall = recall_score(
        true_labels,
        predicted_labels,
        labels=species_names,
        average="macro",
        zero_division=0,
    )

    macro_f1 = f1_score(
        true_labels,
        predicted_labels,
        labels=species_names,
        average="macro",
        zero_division=0,
    )

    weighted_f1 = f1_score(
        true_labels,
        predicted_labels,
        labels=species_names,
        average="weighted",
        zero_division=0,
    )

    micro_f1 = f1_score(
        true_labels,
        predicted_labels,
        labels=species_names,
        average="micro",
        zero_division=0,
    )

    # ========================================================
    # Per-species metrics
    # ========================================================

    report = classification_report(
        true_labels,
        predicted_labels,
        labels=species_names,
        target_names=species_names,
        output_dict=True,
        zero_division=0,
    )

    species_metric_rows: list[
        dict[str, object]
    ] = []

    for species in species_names:
        species_metrics = (
            report[
                species
            ]
        )

        species_metric_rows.append(
            {
                "species": species,
                "precision": float(
                    species_metrics[
                        "precision"
                    ]
                ),
                "recall": float(
                    species_metrics[
                        "recall"
                    ]
                ),
                "f1_score": float(
                    species_metrics[
                        "f1-score"
                    ]
                ),
                "support": int(
                    species_metrics[
                        "support"
                    ]
                ),
            }
        )

    # ========================================================
    # Timing metrics
    # ========================================================

    total_audio_seconds = (
        total_clips
        * CLIP_DURATION_SECONDS
    )

    average_wall_clock_seconds = (
        total_inference_seconds
        / total_clips
    )

    realtime_factor = (
        total_inference_seconds
        / total_audio_seconds
    )

    processing_speed = (
        total_audio_seconds
        / total_inference_seconds
    )

    if confidence_values:
        mean_confidence = (
            sum(confidence_values)
            / len(confidence_values)
        )

        sorted_confidences = sorted(
            confidence_values
        )

        middle = (
            len(sorted_confidences)
            // 2
        )

        if (
            len(sorted_confidences)
            % 2
        ):
            median_confidence = (
                sorted_confidences[
                    middle
                ]
            )

        else:
            median_confidence = (
                (
                    sorted_confidences[
                        middle - 1
                    ]
                    + sorted_confidences[
                        middle
                    ]
                )
                / 2
            )

    else:
        mean_confidence = 0.0
        median_confidence = 0.0

    # ========================================================
    # Save CSV files
    # ========================================================

    predictions_path = (
        PREDICTIONS_DIRECTORY
        / f"e0_predictions{suffix}.csv"
    )

    clip_results_path = (
        RESULTS_DIRECTORY
        / f"e0_clip_results{suffix}.csv"
    )

    species_metrics_path = (
        RESULTS_DIRECTORY
        / f"e0_species_metrics{suffix}.csv"
    )

    overall_metrics_path = (
        RESULTS_DIRECTORY
        / f"e0_metrics{suffix}.csv"
    )

    pd.DataFrame(
        prediction_rows
    ).to_csv(
        predictions_path,
        index=False,
    )

    pd.DataFrame(
        clip_rows
    ).to_csv(
        clip_results_path,
        index=False,
    )

    pd.DataFrame(
        species_metric_rows
    ).to_csv(
        species_metrics_path,
        index=False,
    )

    overall_metrics = {
        "experiment_id": (
            EXPERIMENT_ID
        ),
        "model": (
            "BirdNET Acoustic"
        ),
        "model_version": (
            MODEL_VERSION
        ),
        "backend": (
            MODEL_BACKEND
        ),
        "confidence_threshold": (
            CONFIDENCE_THRESHOLD
        ),
        "top_k": (
            TOP_K
        ),
        "batch_size": (
            arguments.batch_size
        ),
        "n_workers": (
            arguments.workers
        ),
        "n_producers": (
            arguments.producers
        ),
        "species_count": (
            len(species_names)
        ),
        "evaluated_clips": (
            total_clips
        ),
        "top1_correct": (
            correct_top1_count
        ),
        "top1_accuracy": (
            top1_accuracy
        ),
        "top3_accuracy": (
            top3_accuracy
        ),
        "top5_accuracy": (
            top5_accuracy
        ),
        "macro_precision": (
            macro_precision
        ),
        "macro_recall": (
            macro_recall
        ),
        "macro_f1": (
            macro_f1
        ),
        "weighted_f1": (
            weighted_f1
        ),
        "micro_f1": (
            micro_f1
        ),
        "abstentions": (
            abstention_count
        ),
        "abstention_rate": (
            abstention_count
            / total_clips
        ),
        "outside_dataset_predictions": (
            outside_dataset_count
        ),
        "outside_dataset_rate": (
            outside_dataset_count
            / total_clips
        ),
        "mean_top1_confidence": (
            mean_confidence
        ),
        "median_top1_confidence": (
            median_confidence
        ),
        "model_load_seconds": (
            model_load_seconds
        ),
        "total_audio_seconds": (
            total_audio_seconds
        ),
        "total_inference_seconds": (
            total_inference_seconds
        ),
        "average_wall_clock_seconds_per_clip": (
            average_wall_clock_seconds
        ),
        "realtime_factor": (
            realtime_factor
        ),
        "processing_speed_x_realtime": (
            processing_speed
        ),
    }

    with overall_metrics_path.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as output_file:
        writer = csv.DictWriter(
            output_file,
            fieldnames=(
                overall_metrics.keys()
            ),
        )

        writer.writeheader()

        writer.writerow(
            overall_metrics
        )

    # ========================================================
    # Save plots
    # ========================================================

    confusion_matrix_path = (
        save_confusion_matrix(
            true_labels=true_labels,
            predicted_labels=(
                predicted_labels
            ),
            species_names=(
                species_names
            ),
            suffix=suffix,
        )
    )

    f1_chart_path = (
        save_species_f1_chart(
            species_metric_rows=(
                species_metric_rows
            ),
            suffix=suffix,
        )
    )

    # ========================================================
    # Console report
    # ========================================================

    print()
    print(
        "=" * 60
    )

    print(
        "E0 RESULTS"
    )

    print(
        "=" * 60
    )

    print(
        f"Evaluated clips: "
        f"{total_clips}"
    )

    print(
        f"Species: "
        f"{len(species_names)}"
    )

    print()
    print(
        "Classification"
    )

    print(
        "-" * 60
    )

    print(
        f"Top-1 accuracy: "
        f"{top1_accuracy:.4f}"
    )

    print(
        f"Top-3 accuracy: "
        f"{top3_accuracy:.4f}"
    )

    print(
        f"Top-5 accuracy: "
        f"{top5_accuracy:.4f}"
    )

    print()

    print(
        f"Macro precision: "
        f"{macro_precision:.4f}"
    )

    print(
        f"Macro recall: "
        f"{macro_recall:.4f}"
    )

    print(
        f"Macro F1: "
        f"{macro_f1:.4f}"
    )

    print(
        f"Weighted F1: "
        f"{weighted_f1:.4f}"
    )

    print(
        f"Micro F1: "
        f"{micro_f1:.4f}"
    )

    print()
    print(
        "Detection behaviour"
    )

    print(
        "-" * 60
    )

    print(
        f"Correct top-1: "
        f"{correct_top1_count}/"
        f"{total_clips}"
    )

    print(
        f"Abstentions: "
        f"{abstention_count} "
        f"({abstention_count / total_clips:.2%})"
    )

    print(
        "Outside-dataset predictions: "
        f"{outside_dataset_count} "
        f"({outside_dataset_count / total_clips:.2%})"
    )

    print(
        "Mean top-1 confidence: "
        f"{mean_confidence:.4f}"
    )

    print(
        "Median top-1 confidence: "
        f"{median_confidence:.4f}"
    )

    print()
    print(
        "Performance"
    )

    print(
        "-" * 60
    )

    print(
        f"Model load time: "
        f"{model_load_seconds:.3f} s"
    )

    print(
        f"Total audio: "
        f"{total_audio_seconds:.1f} s"
    )

    print(
        f"Inference wall time: "
        f"{total_inference_seconds:.3f} s"
    )

    print(
        "Average wall-clock time / clip: "
        f"{average_wall_clock_seconds:.4f} s"
    )

    print(
        f"Real-time factor: "
        f"{realtime_factor:.4f}"
    )

    print(
        f"Processing speed: "
        f"{processing_speed:.2f}x real-time"
    )

    print()
    print(
        "Per-species performance"
    )

    print(
        "-" * 60
    )

    print(
        f"{'Species':<35}"
        f"{'Precision':>10}"
        f"{'Recall':>10}"
        f"{'F1':>10}"
    )

    for row in species_metric_rows:
        print(
            f"{str(row['species']):<35}"
            f"{float(row['precision']):>10.3f}"
            f"{float(row['recall']):>10.3f}"
            f"{float(row['f1_score']):>10.3f}"
        )

    print()
    print(
        "Generated files"
    )

    print(
        "-" * 60
    )

    print(
        f"Overall metrics:\n"
        f"  {overall_metrics_path}"
    )

    print(
        f"Species metrics:\n"
        f"  {species_metrics_path}"
    )

    print(
        f"Clip results:\n"
        f"  {clip_results_path}"
    )

    print(
        f"All predictions:\n"
        f"  {predictions_path}"
    )

    print(
        f"Confusion matrix:\n"
        f"  {confusion_matrix_path}"
    )

    print(
        f"Species F1 chart:\n"
        f"  {f1_chart_path}"
    )


if __name__ == "__main__":
    main()

