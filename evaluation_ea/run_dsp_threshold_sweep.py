"""
DSP-only ROI threshold sweep.

Tests multiple ROI threshold factors without running BirdNET.

Thresholds:
    0.75
    1.00
    1.25
    1.50
    1.75

For each threshold:
    - Process all soundscape recordings
    - Extract DSP ROIs
    - Calculate retained acoustic duration
    - Calculate BirdNET input duration
    - Calculate audio reduction
    - Calculate ROI recall against known-species annotations
    - Calculate mean temporal coverage
    - Count completely missed events
    - Count fully covered events

Outputs:
    evaluation_ea/results/threshold_sweep/
        threshold_comparison.csv
        threshold_0_75/
        threshold_1_00/
        threshold_1_25/
        threshold_1_50/
        threshold_1_75/
"""

from pathlib import Path
import sys
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from backend.src.services.audio_processing import (
    AudioProcessingService,
)


# ============================================================
# Configuration
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

SOUNDSCAPE_DIR = (
    BASE_DIR / "soundscape_data"
)

ANNOTATIONS_FILE = (
    BASE_DIR / "annotations.csv"
)

OUTPUT_DIR = (
    BASE_DIR / "results" / "threshold_sweep"
)

THRESHOLDS = [
    0.75,
    1.00,
    1.25,
    1.50,
    1.75,
]


# ============================================================
# Helper functions
# ============================================================

def calculate_iou(
    start_a,
    end_a,
    start_b,
    end_b,
):
    """Calculate temporal intersection-over-union."""

    intersection_start = max(
        start_a,
        start_b,
    )

    intersection_end = min(
        end_a,
        end_b,
    )

    intersection = max(
        0.0,
        intersection_end - intersection_start,
    )

    duration_a = max(
        0.0,
        end_a - start_a,
    )

    duration_b = max(
        0.0,
        end_b - start_b,
    )

    union = (
        duration_a
        + duration_b
        - intersection
    )

    if union <= 0.0:
        return 0.0

    return intersection / union


def calculate_union_coverage(
    gt_start,
    gt_end,
    roi_intervals,
):
    """
    Calculate the fraction of a ground-truth interval
    covered by the union of all overlapping ROIs.
    """

    gt_duration = gt_end - gt_start

    if gt_duration <= 0.0:
        return 0.0

    intersections = []

    for roi_start, roi_end in roi_intervals:

        overlap_start = max(
            gt_start,
            roi_start,
        )

        overlap_end = min(
            gt_end,
            roi_end,
        )

        if overlap_end > overlap_start:

            intersections.append(
                (
                    overlap_start,
                    overlap_end,
                )
            )

    if not intersections:
        return 0.0

    # Sort intervals by start time.
    intersections.sort(
        key=lambda x: x[0]
    )

    # Merge overlapping intervals.
    merged = []

    current_start, current_end = (
        intersections[0]
    )

    for start, end in intersections[1:]:

        if start <= current_end:

            current_end = max(
                current_end,
                end,
            )

        else:

            merged.append(
                (
                    current_start,
                    current_end,
                )
            )

            current_start = start
            current_end = end

    merged.append(
        (
            current_start,
            current_end,
        )
    )

    covered_duration = sum(
        end - start
        for start, end in merged
    )

    return min(
        1.0,
        covered_duration / gt_duration,
    )


def safe_float(value):
    """Convert a value to float safely."""

    return float(value)


# ============================================================
# Load annotations
# ============================================================

def load_annotations():

    annotations = pd.read_csv(
        ANNOTATIONS_FILE
    )

    # Remove accidental whitespace from column names.
    annotations.columns = [
        str(column).strip()
        for column in annotations.columns
    ]

    required_columns = [
        "Filename",
        "Start Time (s)",
        "End Time (s)",
        "Species eBird Code",
    ]

    missing_columns = [
        column
        for column in required_columns
        if column not in annotations.columns
    ]

    if missing_columns:

        raise ValueError(
            "Missing required annotation columns: "
            + ", ".join(missing_columns)
            + "\n\nAvailable columns:\n"
            + "\n".join(
                annotations.columns
            )
        )

    # Known species:
    # exclude rows without a species code
    # and the explicit unknown code ????.
    known_annotations = annotations[
        annotations["Species eBird Code"]
        .notna()
        &
        (
            annotations["Species eBird Code"]
            .astype(str)
            .str.strip()
            != "????"
        )
    ].copy()

    return (
        annotations,
        known_annotations,
    )


# ============================================================
# Process one threshold
# ============================================================

def run_threshold(
    threshold,
    known_annotations,
):
    """Run DSP and evaluation for one threshold."""

    print()
    print("=" * 75)
    print(
        f"THRESHOLD {threshold:.2f}"
    )
    print("=" * 75)

    print(
        f"ROI threshold factor: "
        f"{threshold:.2f}"
    )

    service = AudioProcessingService(
        roi_threshold_factor=threshold,
    )

    recording_files = sorted(
        SOUNDSCAPE_DIR.glob("*.flac")
    )

    if not recording_files:

        raise FileNotFoundError(
            "No FLAC recordings found in:\n"
            f"{SOUNDSCAPE_DIR}"
        )

    print(
        f"Found {len(recording_files)} "
        "FLAC recordings."
    )

    total_original_duration = 0.0

    total_roi_acoustic_duration = 0.0

    total_birdnet_input_duration = 0.0

    total_roi_count = 0

    all_rois = []

    # --------------------------------------------------------
    # DSP processing
    # --------------------------------------------------------

    for index, audio_file in enumerate(
        recording_files,
        start=1,
    ):

        print()
        print(
            f"[{index:02d}/{len(recording_files)}] "
            f"{audio_file.name}"
        )

        result = service.process(
            audio_file
        )

        recording_duration = (
            result.duration_seconds
        )

        roi_count = len(
            result.rois
        )

        acoustic_duration = sum(
            roi.original_duration_seconds
            for roi in result.rois
        )

        birdnet_duration = sum(
            len(roi.audio)
            / result.sample_rate
            for roi in result.rois
        )

        total_original_duration += (
            recording_duration
        )

        total_roi_acoustic_duration += (
            acoustic_duration
        )

        total_birdnet_input_duration += (
            birdnet_duration
        )

        total_roi_count += roi_count

        print(
            f"    Duration: "
            f"{recording_duration / 3600:.3f} h"
            f" | ROIs: {roi_count}"
            f" | ROI audio: "
            f"{acoustic_duration:.2f} s"
        )

        for roi in result.rois:

            all_rois.append(
                {
                    "filename": audio_file.name,
                    "start_seconds": (
                        roi.region.start_time
                    ),
                    "end_seconds": (
                        roi.region.end_time
                    ),
                    "original_duration_seconds": (
                        roi.original_duration_seconds
                    ),
                    "birdnet_input_duration_seconds": (
                        len(roi.audio)
                        / result.sample_rate
                    ),
                }
            )

    # --------------------------------------------------------
    # Reduction metrics
    # --------------------------------------------------------

    original_hours = (
        total_original_duration / 3600.0
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
        1.0
        - (
            total_roi_acoustic_duration
            / total_original_duration
        )
    ) * 100.0

    birdnet_reduction = (
        1.0
        - (
            total_birdnet_input_duration
            / total_original_duration
        )
    ) * 100.0

    # --------------------------------------------------------
    # ROI coverage
    # --------------------------------------------------------

    print()
    print(
        "Calculating ground-truth ROI coverage..."
    )

    rois_by_filename = {}

    for roi in all_rois:

        filename = roi["filename"]

        if filename not in rois_by_filename:

            rois_by_filename[
                filename
            ] = []

        rois_by_filename[
            filename
        ].append(
            (
                roi["start_seconds"],
                roi["end_seconds"],
            )
        )

    coverage_values = []

    captured_events = 0
    missed_events = 0
    measurable_events = 0
    full_coverage_events = 0

    coverage_records = []

    for _, annotation in (
        known_annotations.iterrows()
    ):

        filename = str(
            annotation["Filename"]
        ).strip()

        gt_start = safe_float(
            annotation["Start Time (s)"]
        )

        gt_end = safe_float(
            annotation["End Time (s)"]
        )

        roi_intervals = (
            rois_by_filename.get(
                filename,
                [],
            )
        )

        coverage = (
            calculate_union_coverage(
                gt_start,
                gt_end,
                roi_intervals,
            )
        )

        measurable = (
            gt_end > gt_start
        )

        if measurable:

            measurable_events += 1

            coverage_values.append(
                coverage
            )

            if coverage > 0.0:

                captured_events += 1

            else:

                missed_events += 1

            if coverage >= 1.0:

                full_coverage_events += 1

        coverage_records.append(
            {
                "filename": filename,
                "gt_start_seconds": gt_start,
                "gt_end_seconds": gt_end,
                "gt_duration_seconds": max(
                    0.0,
                    gt_end - gt_start,
                ),
                "measurable": measurable,
                "coverage": coverage,
            }
        )

    if coverage_values:

        mean_coverage = float(
            np.mean(
                coverage_values
            )
        )

    else:

        mean_coverage = 0.0

    roi_recall = (
        captured_events
        / measurable_events
        if measurable_events > 0
        else 0.0
    )

    zero_coverage_events = (
        missed_events
    )

    # --------------------------------------------------------
    # Save detailed results for threshold
    # --------------------------------------------------------

    threshold_name = (
        f"threshold_{threshold:.2f}"
        .replace(".", "_")
    )

    threshold_output_dir = (
        OUTPUT_DIR / threshold_name
    )

    threshold_output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    roi_df = pd.DataFrame(
        all_rois
    )

    roi_df.to_csv(
        threshold_output_dir / "rois.csv",
        index=False,
    )

    coverage_df = pd.DataFrame(
        coverage_records
    )

    coverage_df.to_csv(
        threshold_output_dir
        / "roi_temporal_coverage.csv",
        index=False,
    )

    # --------------------------------------------------------
    # Print threshold result
    # --------------------------------------------------------

    print()
    print(
        f"THRESHOLD {threshold:.2f} RESULTS"
    )
    print("-" * 75)

    print(
        f"Original audio       : "
        f"{original_hours:.3f} hours"
    )

    print(
        f"ROI count            : "
        f"{total_roi_count:,}"
    )

    print(
        f"Acoustic ROI audio   : "
        f"{acoustic_hours:.3f} hours"
    )

    print(
        f"BirdNET input audio  : "
        f"{birdnet_hours:.3f} hours"
    )

    print(
        f"Acoustic reduction   : "
        f"{acoustic_reduction:.2f}%"
    )

    print(
        f"BirdNET reduction    : "
        f"{birdnet_reduction:.2f}%"
    )

    print()

    print(
        f"Known GT events      : "
        f"{len(known_annotations):,}"
    )

    print(
        f"Measurable GT events : "
        f"{measurable_events:,}"
    )

    print(
        f"Captured by ROI      : "
        f"{captured_events:,}"
    )

    print(
        f"Missed by ROI        : "
        f"{missed_events:,}"
    )

    print(
        f"ROI recall           : "
        f"{roi_recall * 100:.2f}%"
    )

    print(
        f"Mean GT coverage     : "
        f"{mean_coverage * 100:.2f}%"
    )

    print(
        f"0% coverage events   : "
        f"{zero_coverage_events:,}"
    )

    print(
        f"100% coverage events : "
        f"{full_coverage_events:,}"
    )

    # --------------------------------------------------------
    # Return summary
    # --------------------------------------------------------

    return {
        "threshold": threshold,
        "original_audio_hours": original_hours,
        "roi_count": total_roi_count,
        "roi_acoustic_audio_hours": (
            acoustic_hours
        ),
        "birdnet_input_hours": (
            birdnet_hours
        ),
        "acoustic_audio_reduction_percent": (
            acoustic_reduction
        ),
        "birdnet_input_reduction_percent": (
            birdnet_reduction
        ),
        "known_gt_events": len(
            known_annotations
        ),
        "measurable_gt_events": (
            measurable_events
        ),
        "captured_gt_events": (
            captured_events
        ),
        "missed_gt_events": (
            missed_events
        ),
        "roi_recall_percent": (
            roi_recall * 100.0
        ),
        "mean_gt_coverage_percent": (
            mean_coverage * 100.0
        ),
        "zero_coverage_events": (
            zero_coverage_events
        ),
        "full_coverage_events": (
            full_coverage_events
        ),
    }


# ============================================================
# Main
# ============================================================

def main():

    print("=" * 75)
    print(
        "DSP-ONLY ROI THRESHOLD SWEEP"
    )
    print("=" * 75)

    print()
    print(
        "Thresholds:"
    )

    for threshold in THRESHOLDS:

        print(
            f"  {threshold:.2f}"
        )

    print()
    print(
        "BirdNET will NOT be run."
    )

    print(
        f"Soundscape directory:"
        f"\n  {SOUNDSCAPE_DIR}"
    )

    print(
        f"\nOutput directory:"
        f"\n  {OUTPUT_DIR}"
    )

    # --------------------------------------------------------
    # Load annotations
    # --------------------------------------------------------

    (
        annotations,
        known_annotations,
    ) = load_annotations()

    print()
    print(
        f"Total annotations: "
        f"{len(annotations):,}"
    )

    print(
        f"Known-species annotations: "
        f"{len(known_annotations):,}"
    )

    # --------------------------------------------------------
    # Create output directory
    # --------------------------------------------------------

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    # --------------------------------------------------------
    # Run thresholds
    # --------------------------------------------------------

    results = []

    for threshold in THRESHOLDS:

        summary = run_threshold(
            threshold,
            known_annotations,
        )

        results.append(
            summary
        )

    # --------------------------------------------------------
    # Save comparison CSV
    # --------------------------------------------------------

    comparison_df = pd.DataFrame(
        results
    )

    comparison_df = (
        comparison_df.sort_values(
            "threshold"
        )
        .reset_index(drop=True)
    )

    comparison_file = (
        OUTPUT_DIR
        / "threshold_comparison.csv"
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
        "THRESHOLD SWEEP COMPLETE"
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
        "roi_recall_percent",
        "mean_gt_coverage_percent",
        "zero_coverage_events",
        "full_coverage_events",
    ]

    print(
        comparison_df[
            display_columns
        ].to_string(
            index=False,
            float_format=lambda x:
                f"{x:.2f}",
        )
    )

    print()
    print(
        "Saved comparison CSV:"
    )
    print(
        f"  {comparison_file}"
    )


if __name__ == "__main__":
    main()