from __future__ import annotations

import asyncio
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import pandas as pd
import soundfile as sf


# ============================================================
# Project paths
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]

BACKEND_DIRECTORY = (
    PROJECT_ROOT / "backend"
)

EVALUATION_DIRECTORY = (
    PROJECT_ROOT / "evaluation_ea"
)

ANNOTATIONS_FILE = (
    EVALUATION_DIRECTORY / "annotations.csv"
)

SPECIES_FILE = (
    EVALUATION_DIRECTORY / "species.csv"
)

SOUNDCAPE_DIRECTORY = (
    EVALUATION_DIRECTORY / "soundscape_data"
)

RESULTS_DIRECTORY = (
    EVALUATION_DIRECTORY / "results"
)

RAW_PREDICTIONS_FILE = (
    RESULTS_DIRECTORY / "raw_birdnet_predictions.csv"
)

ROI_FILE = (
    RESULTS_DIRECTORY / "pipeline_rois.csv"
)

PIPELINE_PREDICTIONS_FILE = (
    RESULTS_DIRECTORY / "pipeline_birdnet_predictions.csv"
)

GROUND_TRUTH_FILE = (
    RESULTS_DIRECTORY / "ground_truth.csv"
)

SUMMARY_FILE = (
    RESULTS_DIRECTORY / "evaluation_summary.csv"
)

EXCEL_FILE = (
    RESULTS_DIRECTORY / "evaluation_results.xlsx"
)


# ============================================================
# Make backend imports available
# ============================================================

if str(BACKEND_DIRECTORY) not in sys.path:
    sys.path.insert(
        0,
        str(BACKEND_DIRECTORY),
    )


from src.core.config import settings
from src.services.audio_processing import (
    AudioProcessingService,
)
from src.services.birdnet import (
    BirdNetService,
)


# ============================================================
# Utility functions
# ============================================================


def require_file(path: Path) -> None:
    """Raise a clear error if a required file does not exist."""

    if not path.exists():
        raise FileNotFoundError(
            f"Required file does not exist:\n{path}"
        )

    if not path.is_file():
        raise FileNotFoundError(
            f"Required path is not a file:\n{path}"
        )


def require_directory(path: Path) -> None:
    """Raise a clear error if a required directory does not exist."""

    if not path.exists():
        raise FileNotFoundError(
            f"Required directory does not exist:\n{path}"
        )

    if not path.is_dir():
        raise NotADirectoryError(
            f"Required path is not a directory:\n{path}"
        )


def find_audio_files() -> list[Path]:
    """
    Discover all FLAC recordings in the evaluation dataset.
    """

    require_directory(
        SOUNDCAPE_DIRECTORY
    )

    files = sorted(
        SOUNDCAPE_DIRECTORY.glob("*.flac")
    )

    if not files:
        raise FileNotFoundError(
            "No .flac files were found in:\n"
            f"{SOUNDCAPE_DIRECTORY}"
        )

    return files


def safe_float(value: Any) -> float | None:
    """Convert a value to float where possible."""

    if pd.isna(value):
        return None

    try:
        return float(value)
    except (
        TypeError,
        ValueError,
    ):
        return None


# ============================================================
# Dataset loading
# ============================================================


def load_ground_truth() -> pd.DataFrame:
    """
    Load annotations.csv and join species information from
    species.csv.
    """

    require_file(
        ANNOTATIONS_FILE
    )

    require_file(
        SPECIES_FILE
    )

    annotations = pd.read_csv(
        ANNOTATIONS_FILE
    )

    species = pd.read_csv(
        SPECIES_FILE
    )

    required_annotation_columns = {
        "Filename",
        "Start Time (s)",
        "End Time (s)",
        "Low Freq (Hz)",
        "High Freq (Hz)",
        "Species eBird Code",
    }

    missing_annotation_columns = (
        required_annotation_columns
        - set(annotations.columns)
    )

    if missing_annotation_columns:
        raise ValueError(
            "annotations.csv is missing required "
            f"columns: {sorted(missing_annotation_columns)}"
        )

    required_species_columns = {
        "Species eBird Code",
        "Scientific Name",
        "Common Name",
    }

    missing_species_columns = (
        required_species_columns
        - set(species.columns)
    )

    if missing_species_columns:
        raise ValueError(
            "species.csv is missing required "
            f"columns: {sorted(missing_species_columns)}"
        )

    ground_truth = annotations.merge(
        species[
            [
                "Species eBird Code",
                "Scientific Name",
                "Common Name",
            ]
        ],
        on="Species eBird Code",
        how="left",
        validate="many_to_one",
    )

    ground_truth = ground_truth.rename(
        columns={
            "Filename": "filename",
            "Start Time (s)": "start_time_seconds",
            "End Time (s)": "end_time_seconds",
            "Low Freq (Hz)": "low_frequency_hz",
            "High Freq (Hz)": "high_frequency_hz",
            "Species eBird Code": "species_ebird_code",
            "Scientific Name": "scientific_name",
            "Common Name": "common_name",
        }
    )

    ground_truth[
        "duration_seconds"
    ] = (
        ground_truth[
            "end_time_seconds"
        ]
        - ground_truth[
            "start_time_seconds"
        ]
    )

    ground_truth.insert(
        0,
        "ground_truth_id",
        range(
            1,
            len(ground_truth) + 1,
        ),
    )

    return ground_truth


# ============================================================
# Baseline BirdNET
# ============================================================


async def run_raw_birdnet(
    audio_files: list[Path],
) -> tuple[pd.DataFrame, float]:
    """
    Run BirdNET directly on the original recordings.

    This is the baseline condition.
    """

    birdnet_service = (
        BirdNetService()
    )

    print()
    print("=" * 70)
    print("BASELINE: RAW AUDIO → BIRDNET")
    print("=" * 70)

    print(
        f"BirdNET model: {settings.birdnet_model_name}"
    )

    print(
        f"BirdNET version: {settings.birdnet_model_version}"
    )

    print(
        f"Backend: {settings.birdnet_backend}"
    )

    print(
        f"Minimum confidence: "
        f"{settings.birdnet_min_confidence}"
    )

    print(
        f"Maximum predictions/interval: "
        f"{settings.birdnet_max_predictions_per_interval}"
    )

    start_time = time.perf_counter()

    predictions_by_path = (
        await birdnet_service.analyze_batch(
            audio_files
        )
    )

    elapsed_seconds = (
        time.perf_counter()
        - start_time
    )

    rows: list[dict[str, Any]] = []

    prediction_id = 1

    for audio_path in audio_files:
        predictions = (
            predictions_by_path.get(
                audio_path,
                [],
            )
        )

        for prediction in predictions:
            rows.append(
                {
                    "prediction_id": prediction_id,
                    "filename": audio_path.name,
                    "file_path": str(
                        audio_path
                    ),
                    "start_time_seconds": (
                        prediction
                        .start_time_seconds
                    ),
                    "end_time_seconds": (
                        prediction
                        .end_time_seconds
                    ),
                    "duration_seconds": (
                        prediction
                        .end_time_seconds
                        - prediction
                        .start_time_seconds
                    ),
                    "scientific_name": (
                        prediction
                        .scientific_name
                    ),
                    "common_name": (
                        prediction
                        .common_name
                    ),
                    "confidence": (
                        prediction
                        .confidence
                    ),
                    "source": "raw",
                }
            )

            prediction_id += 1

    predictions_df = pd.DataFrame(
        rows
    )

    return (
        predictions_df,
        elapsed_seconds,
    )


# ============================================================
# Proposed ROI pipeline
# ============================================================


async def run_roi_pipeline(
    audio_files: list[Path],
) -> tuple[
    pd.DataFrame,
    pd.DataFrame,
    float,
    float,
]:
    """
    Run the existing AudioProcessingService followed by the
    existing batched BirdNetService.

    Returns:

        ROI dataframe
        Pipeline BirdNET predictions dataframe
        Total pipeline processing time
        Total BirdNET input duration
    """

    audio_processing = (
        AudioProcessingService()
    )

    birdnet_service = (
        BirdNetService()
    )

    roi_rows: list[dict[str, Any]] = []

    prediction_rows: list[
        dict[str, Any]
    ] = []

    total_processing_start = (
        time.perf_counter()
    )

    total_birdnet_input_duration = (
        0.0
    )

    prediction_id = 1

    print()
    print("=" * 70)
    print("PROPOSED: AUDIO PROCESSING → ROIs → BIRDNET")
    print("=" * 70)

    print(
        f"ROI threshold factor: "
        f"{audio_processing.roi_threshold_factor}"
    )

    print(
        f"ROI minimum duration: "
        f"{audio_processing.roi_min_duration} s"
    )

    print(
        f"ROI merge gap: "
        f"{audio_processing.roi_merge_gap} s"
    )

    print(
        f"ROI padding: "
        f"{audio_processing.roi_padding} s"
    )

    print(
        f"High-pass cutoff: "
        f"{audio_processing.highpass_cutoff} Hz"
    )

    print(
        f"High-pass order: "
        f"{audio_processing.highpass_filter_order}"
    )

    print(
        f"BirdNET minimum duration: "
        f"{audio_processing.birdnet_min_duration} s"
    )

    # --------------------------------------------------------
    # Temporary directory for generated ROI WAV files
    # --------------------------------------------------------

    temporary_directory = Path(
        tempfile.mkdtemp(
            prefix="birdcall_evaluation_"
        )
    )

    try:
        all_roi_paths: list[Path] = []

        roi_path_to_metadata: dict[
            Path,
            dict[str, Any],
        ] = {}

        # ----------------------------------------------------
        # Process every original recording
        # ----------------------------------------------------

        for file_index, audio_path in enumerate(
            audio_files,
            start=1,
        ):
            print()
            print(
                f"[{file_index}/{len(audio_files)}] "
                f"Processing {audio_path.name}"
            )

            recording_result = (
                await asyncio.to_thread(
                    audio_processing.process,
                    audio_path,
                )
            )

            print(
                f"  Original duration: "
                f"{recording_result.duration_seconds:.2f} s"
            )

            print(
                f"  ROIs detected: "
                f"{len(recording_result.rois)}"
            )

            for roi in (
                recording_result.rois
            ):
                roi_filename = (
                    f"{file_index:03d}_"
                    f"roi_{roi.index:04d}.wav"
                )

                roi_path = (
                    temporary_directory
                    / roi_filename
                )

                await asyncio.to_thread(
                    sf.write,
                    roi_path,
                    roi.audio,
                    recording_result.sample_rate,
                    subtype="PCM_16",
                )

                stored_duration = (
                    len(roi.audio)
                    / recording_result.sample_rate
                )

                original_duration = (
                    roi.original_duration_seconds
                )

                roi_rows.append(
                    {
                        "filename": audio_path.name,
                        "file_path": str(
                            audio_path
                        ),
                        "roi_id": roi.index,
                        "roi_start_seconds": (
                            roi.region.start_time
                        ),
                        "roi_end_seconds": (
                            roi.region.end_time
                        ),
                        "roi_original_duration_seconds": (
                            original_duration
                        ),
                        "roi_birdnet_input_duration_seconds": (
                            stored_duration
                        ),
                        "padding_applied": (
                            original_duration
                            < audio_processing.birdnet_min_duration
                        ),
                        "sample_rate": (
                            recording_result.sample_rate
                        ),
                        "energy_threshold": (
                            recording_result.energy_threshold
                        ),
                        "temporary_roi_path": str(
                            roi_path
                        ),
                    }
                )

                all_roi_paths.append(
                    roi_path
                )

                roi_path_to_metadata[
                    roi_path.resolve()
                ] = {
                    "filename": audio_path.name,
                    "roi_id": roi.index,
                    "roi_start_seconds": (
                        roi.region.start_time
                    ),
                    "roi_end_seconds": (
                        roi.region.end_time
                    ),
                }

                total_birdnet_input_duration += (
                    stored_duration
                )

        # ----------------------------------------------------
        # Run ONE batched BirdNET operation for all ROIs
        # ----------------------------------------------------

        print()
        print(
            f"Running BirdNET on "
            f"{len(all_roi_paths)} ROI files..."
        )

        birdnet_start = (
            time.perf_counter()
        )

        if all_roi_paths:
            predictions_by_path = (
                await birdnet_service.analyze_batch(
                    all_roi_paths
                )
            )
        else:
            predictions_by_path = {}

        birdnet_elapsed = (
            time.perf_counter()
            - birdnet_start
        )

        # ----------------------------------------------------
        # Convert ROI-relative timestamps to original
        # recording timestamps
        # ----------------------------------------------------

        for roi_path in all_roi_paths:
            resolved_roi_path = (
                roi_path.resolve()
            )

            metadata = (
                roi_path_to_metadata[
                    resolved_roi_path
                ]
            )

            predictions = (
                predictions_by_path.get(
                    resolved_roi_path,
                    [],
                )
            )

            # ------------------------------------------------
            # Some path implementations may return the exact
            # Path object rather than its resolved equivalent.
            # Try the original path as a fallback.
            # ------------------------------------------------

            if not predictions:
                predictions = (
                    predictions_by_path.get(
                        roi_path,
                        [],
                    )
                )

            for prediction in predictions:
                absolute_start = (
                    metadata[
                        "roi_start_seconds"
                    ]
                    + prediction.start_time_seconds
                )

                absolute_end = (
                    metadata[
                        "roi_start_seconds"
                    ]
                    + prediction.end_time_seconds
                )

                prediction_rows.append(
                    {
                        "prediction_id": prediction_id,
                        "filename": metadata[
                            "filename"
                        ],
                        "roi_id": metadata[
                            "roi_id"
                        ],
                        "roi_start_seconds": metadata[
                            "roi_start_seconds"
                        ],
                        "roi_end_seconds": metadata[
                            "roi_end_seconds"
                        ],
                        "start_time_seconds": (
                            absolute_start
                        ),
                        "end_time_seconds": (
                            absolute_end
                        ),
                        "duration_seconds": (
                            absolute_end
                            - absolute_start
                        ),
                        "scientific_name": (
                            prediction
                            .scientific_name
                        ),
                        "common_name": (
                            prediction
                            .common_name
                        ),
                        "confidence": (
                            prediction
                            .confidence
                        ),
                        "source": "pipeline",
                    }
                )

                prediction_id += 1

        total_processing_elapsed = (
            time.perf_counter()
            - total_processing_start
        )

    finally:
        # ----------------------------------------------------
        # Generated ROI files are temporary evaluation files.
        # The detailed CSV keeps the metadata, but the WAVs
        # themselves are removed after evaluation.
        # ----------------------------------------------------

        shutil.rmtree(
            temporary_directory,
            ignore_errors=True,
        )

    roi_df = pd.DataFrame(
        roi_rows
    )

    predictions_df = pd.DataFrame(
        prediction_rows
    )

    return (
        roi_df,
        predictions_df,
        total_processing_elapsed,
        total_birdnet_input_duration,
    )


# ============================================================
# Dataset statistics
# ============================================================


def calculate_dataset_summary(
    audio_files: list[Path],
    ground_truth: pd.DataFrame,
    roi_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Calculate dataset and ROI-reduction statistics.

    No detection matching is performed here.
    """

    total_original_duration = 0.0

    recording_rows: list[
        dict[str, Any]
    ] = []

    for audio_path in audio_files:
        info = sf.info(
            audio_path
        )

        duration = float(
            info.duration
        )

        total_original_duration += (
            duration
        )

        recording_rows.append(
            {
                "filename": audio_path.name,
                "duration_seconds": duration,
            }
        )

    recording_df = pd.DataFrame(
        recording_rows
    )

    if roi_df.empty:
        total_roi_audio_duration = 0.0
        total_birdnet_input_duration = 0.0
    else:
        total_roi_audio_duration = (
            roi_df[
                "roi_original_duration_seconds"
            ]
            .sum()
        )

        total_birdnet_input_duration = (
            roi_df[
                "roi_birdnet_input_duration_seconds"
            ]
            .sum()
        )

    acoustic_reduction_percent = (
        (
            1.0
            - (
                total_roi_audio_duration
                / total_original_duration
            )
        )
        * 100.0
        if total_original_duration > 0
        else 0.0
    )

    birdnet_input_reduction_percent = (
        (
            1.0
            - (
                total_birdnet_input_duration
                / total_original_duration
            )
        )
        * 100.0
        if total_original_duration > 0
        else 0.0
    )

    summary = pd.DataFrame(
        [
            {
                "recordings": len(
                    audio_files
                ),
                "original_audio_hours": (
                    total_original_duration
                    / 3600.0
                ),
                "ground_truth_events": len(
                    ground_truth
                ),
                "roi_count": len(
                    roi_df
                ),
                "roi_acoustic_audio_hours": (
                    total_roi_audio_duration
                    / 3600.0
                ),
                "birdnet_input_hours": (
                    total_birdnet_input_duration
                    / 3600.0
                ),
                "acoustic_audio_reduction_percent": (
                    acoustic_reduction_percent
                ),
                "birdnet_input_reduction_percent": (
                    birdnet_input_reduction_percent
                ),
            }
        ]
    )

    return (
        summary,
        recording_df,
    )


# ============================================================
# Annotation inspection
# ============================================================


def print_annotation_statistics(
    ground_truth: pd.DataFrame,
) -> None:
    """
    Print useful statistics about the ground-truth
    annotations before temporal matching is implemented.
    """

    print()
    print("=" * 70)
    print("GROUND-TRUTH ANNOTATION INSPECTION")
    print("=" * 70)

    if ground_truth.empty:
        print(
            "No ground-truth annotations were found."
        )
        return

    durations = (
        ground_truth[
            "duration_seconds"
        ]
    )

    print(
        f"Ground-truth events: "
        f"{len(ground_truth)}"
    )

    print(
        f"Unique recordings: "
        f"{ground_truth['filename'].nunique()}"
    )

    print(
        f"Unique species codes: "
        f"{ground_truth['species_ebird_code'].nunique()}"
    )

    print()
    print("Annotation duration statistics:")
    print(
        durations.describe()
        .to_string()
    )

    print()
    print(
        "Shortest annotations:"
    )

    print(
        ground_truth[
            [
                "filename",
                "start_time_seconds",
                "end_time_seconds",
                "duration_seconds",
                "common_name",
            ]
        ]
        .sort_values(
            "duration_seconds"
        )
        .head(10)
        .to_string(
            index=False
        )
    )

    print()
    print(
        "Species with most annotations:"
    )

    species_counts = (
        ground_truth.groupby(
            [
                "species_ebird_code",
                "scientific_name",
                "common_name",
            ],
            dropna=False,
        )
        .size()
        .reset_index(
            name="annotation_count"
        )
        .sort_values(
            "annotation_count",
            ascending=False,
        )
    )

    print(
        species_counts.head(20)
        .to_string(
            index=False
        )
    )


# ============================================================
# Main
# ============================================================


async def main() -> None:
    print()
    print("=" * 70)
    print("BIRDCALL MONITORING SYSTEM - EVALUATION")
    print("=" * 70)

    print(
        f"Project root:\n{PROJECT_ROOT}"
    )

    print(
        f"Evaluation directory:\n"
        f"{EVALUATION_DIRECTORY}"
    )

    # --------------------------------------------------------
    # Validate files/directories
    # --------------------------------------------------------

    require_file(
        ANNOTATIONS_FILE
    )

    require_file(
        SPECIES_FILE
    )

    require_directory(
        SOUNDCAPE_DIRECTORY
    )

    RESULTS_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True,
    )

    # --------------------------------------------------------
    # Discover recordings
    # --------------------------------------------------------

    audio_files = (
        find_audio_files()
    )

    print()
    print(
        f"Found {len(audio_files)} FLAC recordings."
    )

    for audio_file in audio_files:
        print(
            f"  - {audio_file.name}"
        )

    # --------------------------------------------------------
    # Load ground truth
    # --------------------------------------------------------

    ground_truth = (
        load_ground_truth()
    )

    print()
    print(
        f"Loaded {len(ground_truth)} "
        f"ground-truth annotations."
    )

    # --------------------------------------------------------
    # Save normalized ground truth
    # --------------------------------------------------------

    ground_truth.to_csv(
        GROUND_TRUTH_FILE,
        index=False,
    )

    # --------------------------------------------------------
    # Print annotation statistics
    # --------------------------------------------------------

    print_annotation_statistics(
        ground_truth
    )

    # --------------------------------------------------------
    # Print actual configuration
    # --------------------------------------------------------

    print()
    print("=" * 70)
    print("EXPERIMENT CONFIGURATION")
    print("=" * 70)

    print(
        f"BirdNET model: "
        f"{settings.birdnet_model_name}"
    )

    print(
        f"BirdNET version: "
        f"{settings.birdnet_model_version}"
    )

    print(
        f"BirdNET backend: "
        f"{settings.birdnet_backend}"
    )

    print(
        f"BirdNET confidence threshold: "
        f"{settings.birdnet_min_confidence}"
    )

    print(
        f"BirdNET max predictions/interval: "
        f"{settings.birdnet_max_predictions_per_interval}"
    )

    print(
        f"BirdNET batch size: "
        f"{settings.birdnet_batch_size}"
    )

    print(
        f"BirdNET workers: "
        f"{settings.birdnet_workers}"
    )

    print(
        f"BirdNET producers: "
        f"{settings.birdnet_producers}"
    )

    print(
        f"BirdNET prefetch ratio: "
        f"{settings.birdnet_prefetch_ratio}"
    )

    # --------------------------------------------------------
    # Baseline
    # --------------------------------------------------------

    raw_predictions, raw_elapsed = (
        await run_raw_birdnet(
            audio_files
        )
    )

    raw_predictions.to_csv(
        RAW_PREDICTIONS_FILE,
        index=False,
    )

    # --------------------------------------------------------
    # Proposed pipeline
    # --------------------------------------------------------

    (
        roi_df,
        pipeline_predictions,
        pipeline_elapsed,
        total_birdnet_input_duration,
    ) = await run_roi_pipeline(
        audio_files
    )

    roi_df.to_csv(
        ROI_FILE,
        index=False,
    )

    pipeline_predictions.to_csv(
        PIPELINE_PREDICTIONS_FILE,
        index=False,
    )

    # --------------------------------------------------------
    # Dataset / ROI statistics
    # --------------------------------------------------------

    (
        dataset_summary,
        recording_durations,
    ) = calculate_dataset_summary(
        audio_files,
        ground_truth,
        roi_df,
    )

    # --------------------------------------------------------
    # Add timing information
    # --------------------------------------------------------

    dataset_summary[
        "raw_birdnet_processing_seconds"
    ] = raw_elapsed

    dataset_summary[
        "pipeline_total_processing_seconds"
    ] = pipeline_elapsed

    dataset_summary[
        "pipeline_birdnet_input_duration_hours"
    ] = (
        total_birdnet_input_duration
        / 3600.0
    )

    # --------------------------------------------------------
    # Prediction counts
    # --------------------------------------------------------

    dataset_summary[
        "raw_prediction_count"
    ] = len(
        raw_predictions
    )

    dataset_summary[
        "pipeline_prediction_count"
    ] = len(
        pipeline_predictions
    )

    # --------------------------------------------------------
    # Save summary
    # --------------------------------------------------------

    dataset_summary.to_csv(
        SUMMARY_FILE,
        index=False,
    )

    # --------------------------------------------------------
    # Create Excel workbook
    # --------------------------------------------------------

    with pd.ExcelWriter(
        EXCEL_FILE,
        engine="openpyxl",
    ) as writer:

        dataset_summary.to_excel(
            writer,
            sheet_name="01_summary",
            index=False,
        )

        recording_durations.to_excel(
            writer,
            sheet_name="02_recordings",
            index=False,
        )

        ground_truth.to_excel(
            writer,
            sheet_name="03_ground_truth",
            index=False,
        )

        raw_predictions.to_excel(
            writer,
            sheet_name="04_raw_birdnet",
            index=False,
        )

        roi_df.to_excel(
            writer,
            sheet_name="05_pipeline_rois",
            index=False,
        )

        pipeline_predictions.to_excel(
            writer,
            sheet_name="06_pipeline_birdnet",
            index=False,
        )

    # --------------------------------------------------------
    # Final console summary
    # --------------------------------------------------------

    print()
    print("=" * 70)
    print("INITIAL EVALUATION COMPLETE")
    print("=" * 70)

    print(
        f"Recordings: "
        f"{len(audio_files)}"
    )

    print(
        f"Ground-truth events: "
        f"{len(ground_truth)}"
    )

    print(
        f"Raw BirdNET predictions: "
        f"{len(raw_predictions)}"
    )

    print(
        f"Detected ROIs: "
        f"{len(roi_df)}"
    )

    print(
        f"Pipeline BirdNET predictions: "
        f"{len(pipeline_predictions)}"
    )

    print()
    print(
        f"Original audio: "
        f"{dataset_summary.iloc[0]['original_audio_hours']:.3f} h"
    )

    print(
        f"Acoustic ROI audio: "
        f"{dataset_summary.iloc[0]['roi_acoustic_audio_hours']:.3f} h"
    )

    print(
        f"BirdNET input audio: "
        f"{dataset_summary.iloc[0]['birdnet_input_hours']:.3f} h"
    )

    print(
        f"Acoustic audio reduction: "
        f"{dataset_summary.iloc[0]['acoustic_audio_reduction_percent']:.2f}%"
    )

    print(
        f"BirdNET input reduction: "
        f"{dataset_summary.iloc[0]['birdnet_input_reduction_percent']:.2f}%"
    )

    print()
    print(
        f"Raw BirdNET processing time: "
        f"{raw_elapsed:.2f} s"
    )

    print(
        f"Pipeline total processing time: "
        f"{pipeline_elapsed:.2f} s"
    )

    print()
    print(
        "Results written to:"
    )

    print(
        f"  {RESULTS_DIRECTORY}"
    )

    print()
    print(
        "Important: TP/FP/FN, Precision, Recall and F1 "
        "have intentionally NOT been calculated yet."
    )

    print(
        "The next step is to inspect the generated "
        "predictions and annotation timing structure and "
        "then implement the fixed temporal matching rule."
    )


if __name__ == "__main__":
    asyncio.run(
        main()
    )