from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd


# ============================================================
# Project paths
# ============================================================

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
# Experiment configuration
# ============================================================

SOUNDSCAPE_DIR = (
    PROJECT_ROOT
    / "evaluation_ea"
    / "soundscape_data"
)

ANNOTATIONS_FILE = (
    PROJECT_ROOT
    / "evaluation_ea"
    / "annotations.csv"
)

OUTPUT_DIR = (
    PROJECT_ROOT
    / "evaluation_ea"
    / "results"
    / "threshold_0_5"
)

THRESHOLD_FACTOR = 0.5


# ============================================================
# Utility functions
# ============================================================

def calculate_overlap(
    start_a: float,
    end_a: float,
    start_b: float,
    end_b: float,
) -> float:
    """
    Calculate temporal overlap between two intervals.
    """

    return max(
        0.0,
        min(end_a, end_b)
        - max(start_a, start_b),
    )


def calculate_iou(
    start_a: float,
    end_a: float,
    start_b: float,
    end_b: float,
) -> float:
    """
    Calculate temporal Intersection over Union.
    """

    intersection = calculate_overlap(
        start_a,
        end_a,
        start_b,
        end_b,
    )

    union = (
        max(end_a, end_b)
        - min(start_a, start_b)
    )

    if union <= 0:
        return 0.0

    return intersection / union


def calculate_union_coverage(
    gt_start: float,
    gt_end: float,
    roi_intervals: list[
        tuple[float, float]
    ],
) -> float:
    """
    Calculate the fraction of a ground-truth event covered
    by the union of overlapping ROIs.

    Coverage is:

        total covered GT duration
        -------------------------
        total GT event duration

    This avoids counting overlapping ROIs multiple times.
    """

    gt_duration = (
        gt_end
        - gt_start
    )

    if gt_duration <= 0:
        return np.nan

    overlapping_intervals = []

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
            overlapping_intervals.append(
                (
                    overlap_start,
                    overlap_end,
                )
            )

    if not overlapping_intervals:
        return 0.0

    # Sort intervals by start time.
    overlapping_intervals.sort(
        key=lambda interval: interval[0]
    )

    # Merge overlapping intervals.
    merged = [
        overlapping_intervals[0]
    ]

    for current_start, current_end in (
        overlapping_intervals[1:]
    ):

        previous_start, previous_end = (
            merged[-1]
        )

        if current_start <= previous_end:

            merged[-1] = (
                previous_start,
                max(
                    previous_end,
                    current_end,
                ),
            )

        else:

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


# ============================================================
# Main experiment
# ============================================================

def main() -> None:

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    print("=" * 75)
    print("DSP-ONLY ROI THRESHOLD EXPERIMENT")
    print("=" * 75)
    print()
    print(
        f"ROI threshold factor: {THRESHOLD_FACTOR}"
    )
    print(
        f"Soundscape directory: {SOUNDSCAPE_DIR}"
    )
    print()

    # --------------------------------------------------------
    # Load ground-truth annotations
    # --------------------------------------------------------

    annotations = pd.read_csv(
        ANNOTATIONS_FILE
    )

    annotations.columns = [
        column.strip()
        for column in annotations.columns
    ]

    print(
        f"Total annotations: {len(annotations):,}"
    )

    # Keep known species only.
    #
    # The existing evaluation has:
    #   16,482 total events
    #   14,798 known-species events
    #
    # Unknown events (????) are excluded from species-related
    # ROI recall.
    known_annotations = annotations[
        annotations[
            "Species eBird Code"
        ]
        .notna()
        & (
            annotations[
                "Species eBird Code"
            ]
            .astype(str)
            .str.strip()
            != "????"
        )
    ].copy()

    print(
        "Known-species annotations: "
        f"{len(known_annotations):,}"
    )
    print()

    # --------------------------------------------------------
    # Create DSP service
    # --------------------------------------------------------

    service = AudioProcessingService(
        roi_threshold_factor=THRESHOLD_FACTOR,
    )

    print("DSP configuration:")
    print(
        f"  Sample rate       : "
        f"{service.sample_rate} Hz"
    )
    print(
        f"  Frame duration    : "
        f"{service.frame_duration} s"
    )
    print(
        f"  Hop duration      : "
        f"{service.hop_duration} s"
    )
    print(
        f"  Threshold factor  : "
        f"{service.roi_threshold_factor}"
    )
    print(
        f"  Minimum ROI       : "
        f"{service.roi_min_duration} s"
    )
    print(
        f"  Merge gap         : "
        f"{service.roi_merge_gap} s"
    )
    print(
        f"  ROI padding       : "
        f"{service.roi_padding} s"
    )
    print(
        f"  High-pass cutoff  : "
        f"{service.highpass_cutoff} Hz"
    )
    print(
        f"  High-pass order   : "
        f"{service.highpass_filter_order}"
    )
    print(
        f"  BirdNET minimum   : "
        f"{service.birdnet_min_duration} s"
    )
    print()

    # --------------------------------------------------------
    # Find recordings
    # --------------------------------------------------------

    audio_files = sorted(
        SOUNDSCAPE_DIR.glob("*.flac")
    )

    if not audio_files:
        raise FileNotFoundError(
            f"No FLAC recordings found in: "
            f"{SOUNDSCAPE_DIR}"
        )

    print(
        f"Found {len(audio_files)} FLAC recordings."
    )
    print()

    # --------------------------------------------------------
    # Process recordings
    # --------------------------------------------------------

    roi_records = []
    recording_records = []

    total_original_duration = 0.0
    total_roi_duration = 0.0
    total_birdnet_duration = 0.0

    for index, audio_file in enumerate(
        audio_files,
        start=1,
    ):

        print(
            f"[{index:02d}/{len(audio_files):02d}] "
            f"{audio_file.name}"
        )

        result = service.process(
            audio_file
        )

        original_duration = (
            result.duration_seconds
        )

        rois = result.rois

        roi_acoustic_duration = sum(
            roi.original_duration_seconds
            for roi in rois
        )

        birdnet_input_duration = sum(
            len(roi.audio)
            / result.sample_rate
            for roi in rois
        )

        roi_count = len(rois)

        total_original_duration += (
            original_duration
        )

        total_roi_duration += (
            roi_acoustic_duration
        )

        total_birdnet_duration += (
            birdnet_input_duration
        )

        recording_records.append(
            {
                "filename": audio_file.name,
                "original_duration_seconds": (
                    original_duration
                ),
                "roi_count": roi_count,
                "roi_acoustic_duration_seconds": (
                    roi_acoustic_duration
                ),
                "birdnet_input_duration_seconds": (
                    birdnet_input_duration
                ),
                "acoustic_reduction_percent": (
                    100.0
                    * (
                        1.0
                        - (
                            roi_acoustic_duration
                            / original_duration
                        )
                    )
                    if original_duration > 0
                    else 0.0
                ),
                "birdnet_input_reduction_percent": (
                    100.0
                    * (
                        1.0
                        - (
                            birdnet_input_duration
                            / original_duration
                        )
                    )
                    if original_duration > 0
                    else 0.0
                ),
            }
        )

        for roi in rois:

            roi_records.append(
                {
                    "filename": audio_file.name,
                    "roi_index": roi.index,
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

        print(
            f"    Duration: "
            f"{original_duration / 3600:.3f} h | "
            f"ROIs: {roi_count:,} | "
            f"ROI audio: "
            f"{roi_acoustic_duration:.2f} s"
        )

    # --------------------------------------------------------
    # Save ROI data
    # --------------------------------------------------------

    roi_df = pd.DataFrame(
        roi_records
    )

    recording_df = pd.DataFrame(
        recording_records
    )

    roi_file = (
        OUTPUT_DIR
        / "rois.csv"
    )

    recording_file = (
        OUTPUT_DIR
        / "recording_summary.csv"
    )

    roi_df.to_csv(
        roi_file,
        index=False,
    )

    recording_df.to_csv(
        recording_file,
        index=False,
    )

    # --------------------------------------------------------
    # ROI recall and temporal coverage
    # --------------------------------------------------------

    print()
    print("=" * 75)
    print("GROUND-TRUTH ROI COVERAGE")
    print("=" * 75)

    # Map each recording to its ROIs.
    rois_by_filename = {}

    if not roi_df.empty:

        for filename, group in (
            roi_df.groupby("filename")
        ):

            rois_by_filename[filename] = [
                (
                    float(row["start_seconds"]),
                    float(row["end_seconds"]),
                )
                for _, row in group.iterrows()
            ]

    coverage_records = []

    captured_events = 0
    missed_events = 0

    measurable_events = 0

    for _, annotation in (
        known_annotations.iterrows()
    ):

        filename = str(
            annotation["Filename"]
        ).strip()

        gt_start = float(
            annotation["Start Time (s)"]
        )

        gt_end = float(
            annotation["End Time (s)"]
        )

        roi_intervals = (
            rois_by_filename.get(
                filename,
                [],
            )
        )

        coverage = calculate_union_coverage(
            gt_start,
            gt_end,
            roi_intervals,
        )

        measurable = (
            gt_end > gt_start
        )

        if measurable:
            measurable_events += 1

            captured = (
                coverage > 0.0
            )

            if captured:
                captured_events += 1
            else:
                missed_events += 1

        else:
            captured = None

        # Best IoU is useful for later comparison.
        best_iou = 0.0

        for roi_start, roi_end in (
            roi_intervals
        ):

            iou = calculate_iou(
                roi_start,
                roi_end,
                gt_start,
                gt_end,
            )

            best_iou = max(
                best_iou,
                iou,
            )

        coverage_records.append(
            {
                "filename": filename,
                "gt_start_seconds": gt_start,
                "gt_end_seconds": gt_end,
                "gt_duration_seconds": (
                    max(
                        0.0,
                        gt_end - gt_start,
                    )
                ),
                "measurable": measurable,
                "captured": captured,
                "coverage": coverage,
                "best_iou": best_iou,
            }
        )

    coverage_df = pd.DataFrame(
        coverage_records
    )

    coverage_file = (
        OUTPUT_DIR
        / "roi_temporal_coverage.csv"
    )

    coverage_df.to_csv(
        coverage_file,
        index=False,
    )

    # --------------------------------------------------------
    # Calculate overall metrics
    # --------------------------------------------------------

    original_hours = (
        total_original_duration
        / 3600.0
    )

    roi_hours = (
        total_roi_duration
        / 3600.0
    )

    birdnet_hours = (
        total_birdnet_duration
        / 3600.0
    )

    acoustic_reduction = (
        100.0
        * (
            1.0
            - (
                total_roi_duration
                / total_original_duration
            )
        )
        if total_original_duration > 0
        else 0.0
    )

    birdnet_reduction = (
        100.0
        * (
            1.0
            - (
                total_birdnet_duration
                / total_original_duration
            )
        )
        if total_original_duration > 0
        else 0.0
    )

    roi_recall = (
        captured_events
        / measurable_events
        if measurable_events > 0
        else 0.0
    )

    measurable_coverage = (
        coverage_df[
            coverage_df["measurable"]
        ]["coverage"]
    )

    mean_coverage = (
        measurable_coverage.mean()
        if not measurable_coverage.empty
        else np.nan
    )

    zero_coverage = (
        (
            measurable_coverage
            == 0.0
        )
        .sum()
        if not measurable_coverage.empty
        else 0
    )

    full_coverage = (
        (
            measurable_coverage
            >= 1.0
        )
        .sum()
        if not measurable_coverage.empty
        else 0
    )

    # --------------------------------------------------------
    # Save overall summary
    # --------------------------------------------------------

    summary = pd.DataFrame(
        [
            {
                "threshold_factor": (
                    THRESHOLD_FACTOR
                ),
                "recordings": (
                    len(audio_files)
                ),
                "original_audio_hours": (
                    original_hours
                ),
                "roi_count": (
                    len(roi_df)
                ),
                "roi_acoustic_audio_hours": (
                    roi_hours
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
                "known_ground_truth_events": (
                    len(known_annotations)
                ),
                "measurable_ground_truth_events": (
                    measurable_events
                ),
                "captured_ground_truth_events": (
                    captured_events
                ),
                "missed_ground_truth_events": (
                    missed_events
                ),
                "roi_recall": (
                    roi_recall
                ),
                "mean_temporal_coverage": (
                    mean_coverage
                ),
                "zero_coverage_events": (
                    int(zero_coverage)
                ),
                "full_coverage_events": (
                    int(full_coverage)
                ),
            }
        ]
    )

    summary_file = (
        OUTPUT_DIR
        / "summary.csv"
    )

    summary.to_csv(
        summary_file,
        index=False,
    )

    # --------------------------------------------------------
    # Print final results
    # --------------------------------------------------------

    print()
    print("=" * 75)
    print("THRESHOLD 0.5 RESULTS")
    print("=" * 75)

    print(
        f"Original audio       : "
        f"{original_hours:.3f} hours"
    )

    print(
        f"ROI count            : "
        f"{len(roi_df):,}"
    )

    print(
        f"Acoustic ROI audio   : "
        f"{roi_hours:.3f} hours"
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

    print()

    print(
        f"Mean GT coverage     : "
        f"{mean_coverage * 100:.2f}%"
    )

    print(
        f"0% coverage events   : "
        f"{zero_coverage:,}"
    )

    print(
        f"100% coverage events : "
        f"{full_coverage:,}"
    )

    print()

    print("Saved:")
    print(f"  {summary_file}")
    print(f"  {recording_file}")
    print(f"  {roi_file}")
    print(f"  {coverage_file}")

    print("=" * 75)


if __name__ == "__main__":
    main()

