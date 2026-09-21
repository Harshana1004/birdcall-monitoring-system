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

SOUNDCAPE_DIRECTORY = (
    EVALUATION_DIRECTORY / "soundscape_data"
)

RESULTS_DIRECTORY = (
    EVALUATION_DIRECTORY / "results"
)

THRESHOLD_SWEEP_DIRECTORY = (
    RESULTS_DIRECTORY / "threshold_sweep"
)

OUTPUT_DIRECTORY = (
    RESULTS_DIRECTORY / "selected_threshold_birdnet_max5"
)


# ============================================================
# Thresholds selected from the DSP-only sweep
# ============================================================

SELECTED_THRESHOLDS = [
    1.00,
    1.25,
]


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
    """Find all evaluation FLAC recordings."""

    require_directory(
        SOUNDCAPE_DIRECTORY
    )

    files = sorted(
        SOUNDCAPE_DIRECTORY.glob("*.flac")
    )

    if not files:
        raise FileNotFoundError(
            "No FLAC recordings were found in:\n"
            f"{SOUNDCAPE_DIRECTORY}"
        )

    return files


def threshold_directory(
    threshold: float,
) -> Path:
    """
    Return the directory containing the DSP-only sweep
    results for a particular threshold.
    """

    name = (
        f"threshold_{threshold:.2f}"
        .replace(".", "_")
    )

    return (
        THRESHOLD_SWEEP_DIRECTORY
        / name
    )


# ============================================================
# Run BirdNET for one selected threshold
# ============================================================


async def run_threshold(
    threshold: float,
    audio_files: list[Path],
) -> dict[str, Any]:
    """
    Run the exact DSP pipeline at one selected threshold and
    then run the existing BirdNET service on all generated ROIs.

    The generated ROI WAV files are temporary and are deleted
    after BirdNET finishes.

    Returns summary information and saves detailed prediction
    and ROI CSV files.
    """

    print()
    print("=" * 75)
    print(
        f"SELECTED THRESHOLD: {threshold:.2f}"
    )
    print("=" * 75)

    print(
        f"ROI threshold factor: {threshold:.2f}"
    )

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
        f"BirdNET minimum confidence: "
        f"{settings.birdnet_min_confidence}"
    )

    print(
        f"BirdNET max predictions/interval: "
        f"{settings.birdnet_max_predictions_per_interval}"
    )

    # --------------------------------------------------------
    # Create exact production DSP service with selected
    # threshold.
    # --------------------------------------------------------

    audio_processing = AudioProcessingService(
        roi_threshold_factor=threshold,
    )

    birdnet_service = BirdNetService()

    threshold_name = (
        f"threshold_{threshold:.2f}"
        .replace(".", "_")
    )

    threshold_output_directory = (
        OUTPUT_DIRECTORY
        / threshold_name
    )

    threshold_output_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    # --------------------------------------------------------
    # Temporary directory for BirdNET-ready ROI WAV files.
    # --------------------------------------------------------

    temporary_directory = Path(
        tempfile.mkdtemp(
            prefix=(
                f"birdcall_threshold_"
                f"{threshold:.2f}_"
            )
        )
    )

    try:

        all_roi_paths: list[Path] = []

        roi_path_to_metadata: dict[
            Path,
            dict[str, Any],
        ] = {}

        roi_rows: list[
            dict[str, Any]
        ] = []

        total_original_duration = 0.0
        total_roi_acoustic_duration = 0.0
        total_birdnet_input_duration = 0.0

        # ----------------------------------------------------
        # DSP processing
        # ----------------------------------------------------

        dsp_start = time.perf_counter()

        print()
        print(
            "Running DSP ROI extraction..."
        )

        for file_index, audio_path in enumerate(
            audio_files,
            start=1,
        ):

            print()
            print(
                f"[{file_index}/{len(audio_files)}] "
                f"{audio_path.name}"
            )

            result = await asyncio.to_thread(
                audio_processing.process,
                audio_path,
            )

            total_original_duration += (
                result.duration_seconds
            )

            print(
                f"  Duration: "
                f"{result.duration_seconds / 3600:.3f} h"
            )

            print(
                f"  ROIs: "
                f"{len(result.rois):,}"
            )

            recording_roi_acoustic_duration = 0.0
            recording_birdnet_duration = 0.0

            for roi in result.rois:

                roi_filename = (
                    f"{file_index:03d}_"
                    f"roi_{roi.index:04d}.wav"
                )

                roi_path = (
                    temporary_directory
                    / roi_filename
                )

                # Save the EXACT audio returned by the
                # production AudioProcessingService.
                await asyncio.to_thread(
                    sf.write,
                    roi_path,
                    roi.audio,
                    result.sample_rate,
                    subtype="PCM_16",
                )

                acoustic_duration = (
                    roi.original_duration_seconds
                )

                birdnet_duration = (
                    len(roi.audio)
                    / result.sample_rate
                )

                recording_roi_acoustic_duration += (
                    acoustic_duration
                )

                recording_birdnet_duration += (
                    birdnet_duration
                )

                total_roi_acoustic_duration += (
                    acoustic_duration
                )

                total_birdnet_input_duration += (
                    birdnet_duration
                )

                roi_rows.append(
                    {
                        "filename": audio_path.name,
                        "roi_id": roi.index,
                        "roi_start_seconds": (
                            roi.region.start_time
                        ),
                        "roi_end_seconds": (
                            roi.region.end_time
                        ),
                        "roi_original_duration_seconds": (
                            acoustic_duration
                        ),
                        "roi_birdnet_input_duration_seconds": (
                            birdnet_duration
                        ),
                        "padding_applied": (
                            acoustic_duration
                            < audio_processing.birdnet_min_duration
                        ),
                        "sample_rate": (
                            result.sample_rate
                        ),
                        "energy_threshold": (
                            result.energy_threshold
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

            print(
                f"  Acoustic ROI audio: "
                f"{recording_roi_acoustic_duration:.2f} s"
            )

            print(
                f"  BirdNET input audio: "
                f"{recording_birdnet_duration:.2f} s"
            )

        dsp_elapsed = (
            time.perf_counter()
            - dsp_start
        )

        # ----------------------------------------------------
        # BirdNET
        # ----------------------------------------------------

        print()
        print(
            "=" * 75
        )

        print(
            f"Running BirdNET on "
            f"{len(all_roi_paths):,} ROI files..."
        )

        birdnet_start = time.perf_counter()

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
        # Convert ROI-relative BirdNET timestamps back to
        # original recording timestamps.
        # ----------------------------------------------------

        prediction_rows: list[
            dict[str, Any]
        ] = []

        prediction_id = 1

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

            # Fallback for implementations returning the
            # original Path object.
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
                        "prediction_id": (
                            prediction_id
                        ),
                        "filename": (
                            metadata[
                                "filename"
                            ]
                        ),
                        "roi_id": (
                            metadata[
                                "roi_id"
                            ]
                        ),
                        "roi_start_seconds": (
                            metadata[
                                "roi_start_seconds"
                            ]
                        ),
                        "roi_end_seconds": (
                            metadata[
                                "roi_end_seconds"
                            ]
                        ),
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
                        "source": (
                            f"pipeline_{threshold:.2f}"
                        ),
                    }
                )

                prediction_id += 1

        predictions_df = pd.DataFrame(
            prediction_rows
        )

        roi_df = pd.DataFrame(
            roi_rows
        )

        # ----------------------------------------------------
        # Save detailed files
        # ----------------------------------------------------

        roi_file = (
            threshold_output_directory
            / "pipeline_rois.csv"
        )

        prediction_file = (
            threshold_output_directory
            / "pipeline_birdnet_predictions.csv"
        )

        roi_df.to_csv(
            roi_file,
            index=False,
        )

        predictions_df.to_csv(
            prediction_file,
            index=False,
        )

        # ----------------------------------------------------
        # Calculate reductions
        # ----------------------------------------------------

        original_hours = (
            total_original_duration
            / 3600.0
        )

        acoustic_hours = (
            total_roi_acoustic_duration
            / 3600.0
        )

        birdnet_hours = (
            total_birdnet_input_duration
            / 3600.0
        )

        acoustic_reduction = (
            (
                1.0
                - (
                    total_roi_acoustic_duration
                    / total_original_duration
                )
            )
            * 100.0
        )

        birdnet_reduction = (
            (
                1.0
                - (
                    total_birdnet_input_duration
                    / total_original_duration
                )
            )
            * 100.0
        )

        # ----------------------------------------------------
        # Summary
        # ----------------------------------------------------

        summary = {
            "threshold": threshold,
            "recordings": len(audio_files),
            "original_audio_hours": original_hours,
            "roi_count": len(roi_df),
            "roi_acoustic_audio_hours": acoustic_hours,
            "birdnet_input_hours": birdnet_hours,
            "acoustic_audio_reduction_percent": (
                acoustic_reduction
            ),
            "birdnet_input_reduction_percent": (
                birdnet_reduction
            ),
            "dsp_processing_seconds": dsp_elapsed,
            "birdnet_processing_seconds": (
                birdnet_elapsed
            ),
            "total_pipeline_processing_seconds": (
                dsp_elapsed
                + birdnet_elapsed
            ),
            "birdnet_prediction_count": (
                len(predictions_df)
            ),
        }

        summary_df = pd.DataFrame(
            [summary]
        )

        summary_file = (
            threshold_output_directory
            / "summary.csv"
        )

        summary_df.to_csv(
            summary_file,
            index=False,
        )

        # ----------------------------------------------------
        # Console results
        # ----------------------------------------------------

        print()
        print("=" * 75)
        print(
            f"THRESHOLD {threshold:.2f} COMPLETE"
        )
        print("=" * 75)

        print(
            f"Original audio             : "
            f"{original_hours:.3f} h"
        )

        print(
            f"ROI count                  : "
            f"{len(roi_df):,}"
        )

        print(
            f"Acoustic ROI audio         : "
            f"{acoustic_hours:.3f} h"
        )

        print(
            f"BirdNET input audio        : "
            f"{birdnet_hours:.3f} h"
        )

        print(
            f"Acoustic reduction         : "
            f"{acoustic_reduction:.2f}%"
        )

        print(
            f"BirdNET input reduction    : "
            f"{birdnet_reduction:.2f}%"
        )

        print(
            f"BirdNET predictions        : "
            f"{len(predictions_df):,}"
        )

        print()
        print(
            f"DSP processing time        : "
            f"{dsp_elapsed:.2f} s"
        )

        print(
            f"BirdNET processing time    : "
            f"{birdnet_elapsed:.2f} s"
        )

        print(
            f"Total pipeline time        : "
            f"{dsp_elapsed + birdnet_elapsed:.2f} s"
        )

        print()
        print(
            "Saved:"
        )

        print(
            f"  {roi_file}"
        )

        print(
            f"  {prediction_file}"
        )

        print(
            f"  {summary_file}"
        )

        return summary

    finally:

        # ----------------------------------------------------
        # Delete temporary ROI WAV files.
        # ----------------------------------------------------

        shutil.rmtree(
            temporary_directory,
            ignore_errors=True,
        )


# ============================================================
# Main
# ============================================================


async def main() -> None:

    print()
    print("=" * 75)
    print(
        "SELECTED DSP THRESHOLDS → BIRDNET EVALUATION"
    )
    print("=" * 75)

    print()
    print(
        "Selected thresholds:"
    )

    for threshold in SELECTED_THRESHOLDS:

        print(
            f"  {threshold:.2f}"
        )

    print()
    print(
        "Raw BirdNET baseline will NOT be rerun."
    )

    print(
        "Only the selected DSP thresholds will be "
        "processed."
    )

    # --------------------------------------------------------
    # Validate directories
    # --------------------------------------------------------

    require_directory(
        SOUNDCAPE_DIRECTORY
    )

    require_directory(
        THRESHOLD_SWEEP_DIRECTORY
    )

    OUTPUT_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True,
    )

    # --------------------------------------------------------
    # Find recordings
    # --------------------------------------------------------

    audio_files = find_audio_files()

    print()
    print(
        f"Found {len(audio_files)} recordings."
    )

    # --------------------------------------------------------
    # Verify that DSP-only sweep results exist.
    # --------------------------------------------------------

    print()
    print(
        "Checking saved DSP sweep results..."
    )

    for threshold in SELECTED_THRESHOLDS:

        directory = threshold_directory(
            threshold
        )

        roi_file = (
            directory / "rois.csv"
        )

        coverage_file = (
            directory
            / "roi_temporal_coverage.csv"
        )

        if not roi_file.exists():

            raise FileNotFoundError(
                "Expected DSP sweep ROI file was not found:\n"
                f"{roi_file}"
            )

        if not coverage_file.exists():

            raise FileNotFoundError(
                "Expected DSP sweep coverage file was not found:\n"
                f"{coverage_file}"
            )

        print(
            f"  {threshold:.2f}: OK"
        )

    # --------------------------------------------------------
    # Run selected thresholds
    # --------------------------------------------------------

    summaries = []

    for threshold in SELECTED_THRESHOLDS:

        summary = await run_threshold(
            threshold,
            audio_files,
        )

        summaries.append(
            summary
        )

    # --------------------------------------------------------
    # Save combined comparison
    # --------------------------------------------------------

    comparison_df = pd.DataFrame(
        summaries
    )

    comparison_df = (
        comparison_df
        .sort_values("threshold")
        .reset_index(drop=True)
    )

    comparison_file = (
        OUTPUT_DIRECTORY
        / "selected_threshold_comparison.csv"
    )

    comparison_df.to_csv(
        comparison_file,
        index=False,
    )

    # --------------------------------------------------------
    # Final comparison
    # --------------------------------------------------------

    print()
    print("=" * 75)
    print(
        "SELECTED THRESHOLD BIRDNET EVALUATION COMPLETE"
    )
    print("=" * 75)

    print()

    display_columns = [
        "threshold",
        "roi_count",
        "roi_acoustic_audio_hours",
        "birdnet_input_hours",
        "acoustic_audio_reduction_percent",
        "birdnet_input_reduction_percent",
        "birdnet_processing_seconds",
        "total_pipeline_processing_seconds",
        "birdnet_prediction_count",
    ]

    print(
        comparison_df[
            display_columns
        ].to_string(
            index=False,
            float_format=lambda x:
                f"{x:.3f}",
        )
    )

    print()
    print(
        "Comparison saved to:"
    )

    print(
        f"  {comparison_file}"
    )


if __name__ == "__main__":
    asyncio.run(
        main()
    )