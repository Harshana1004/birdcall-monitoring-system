import pandas as pd
from pathlib import Path


# ============================================================
# CONFIGURATION
# ============================================================

ANNOTATIONS_FILE = Path("evaluation_ea/annotations.csv")

ROI_FILES = {
    "DSP 1.00": Path(
        "evaluation_ea/results/selected_threshold_birdnet_max5/"
        "threshold_1_00/pipeline_rois.csv"
    ),
    "DSP 1.25": Path(
        "evaluation_ea/results/selected_threshold_birdnet_max5/"
        "threshold_1_25/pipeline_rois.csv"
    ),
}

CUTOFF_HZ = 1000.0


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def interval_overlap(a_start, a_end, b_start, b_end):
    """Calculate temporal overlap between two intervals."""
    return max(
        0.0,
        min(a_end, b_end) - max(a_start, b_start)
    )


def frequency_category(low_freq, high_freq):
    """Classify an annotation relative to the 1 kHz cutoff."""

    if high_freq < CUTOFF_HZ:
        return "Entirely below 1 kHz"

    elif low_freq < CUTOFF_HZ <= high_freq:
        return "Crosses 1 kHz"

    else:
        return "Entirely above 1 kHz"


# ============================================================
# LOAD GROUND TRUTH
# ============================================================

print("=" * 70)
print("HIGH-PASS FILTER IMPACT ANALYSIS")
print(f"Cutoff = {CUTOFF_HZ:.0f} Hz")
print("=" * 70)

gt = pd.read_csv(ANNOTATIONS_FILE)

# Convert numeric fields
for column in [
    "Start Time (s)",
    "End Time (s)",
    "Low Freq (Hz)",
    "High Freq (Hz)",
]:
    gt[column] = pd.to_numeric(
        gt[column],
        errors="coerce"
    )

# Remove rows with missing required values
gt = gt.dropna(
    subset=[
        "Filename",
        "Start Time (s)",
        "End Time (s)",
        "Low Freq (Hz)",
        "High Freq (Hz)",
    ]
).copy()

print(f"\nTotal annotations with valid values: {len(gt):,}")

# Keep only known species
gt = gt[
    (gt["Species eBird Code"] != "????")
    & (gt["Species eBird Code"].str.lower() != "unknown")
].copy()

print(f"Known-species annotations: {len(gt):,}")

# Frequency category
gt["frequency_category"] = gt.apply(
    lambda row: frequency_category(
        row["Low Freq (Hz)"],
        row["High Freq (Hz)"]
    ),
    axis=1
)


# ============================================================
# ANALYZE EACH DSP CONFIGURATION
# ============================================================

for threshold_name, roi_file in ROI_FILES.items():

    print("\n" + "=" * 70)
    print(threshold_name)
    print("=" * 70)

    if not roi_file.exists():
        print("\nROI FILE NOT FOUND:")
        print(roi_file)
        continue

    # --------------------------------------------------------
    # Load ROI data
    # --------------------------------------------------------

    rois = pd.read_csv(roi_file)

    print(f"\nROIs: {len(rois):,}")

    # Exact column names from your actual file
    ROI_FILENAME = "filename"
    ROI_START = "roi_start_seconds"
    ROI_END = "roi_end_seconds"

    # Make sure timing columns are numeric
    rois[ROI_START] = pd.to_numeric(
        rois[ROI_START],
        errors="coerce"
    )

    rois[ROI_END] = pd.to_numeric(
        rois[ROI_END],
        errors="coerce"
    )

    # --------------------------------------------------------
    # Calculate ROI coverage for each GT event
    # --------------------------------------------------------

    coverage = []

    for _, event in gt.iterrows():

        filename = event["Filename"]
        gt_start = event["Start Time (s)"]
        gt_end = event["End Time (s)"]

        event_rois = rois[
            rois[ROI_FILENAME] == filename
        ]

        duration = gt_end - gt_start

        # ----------------------------------------------------
        # Zero-duration annotation
        # ----------------------------------------------------

        if duration <= 0:

            covered = False

            for _, roi in event_rois.iterrows():

                roi_start = roi[ROI_START]
                roi_end = roi[ROI_END]

                if pd.isna(roi_start) or pd.isna(roi_end):
                    continue

                if roi_start <= gt_start <= roi_end:
                    covered = True
                    break

            coverage.append(
                1.0 if covered else 0.0
            )

            continue

        # ----------------------------------------------------
        # Normal annotation
        # ----------------------------------------------------

        total_overlap = 0.0

        for _, roi in event_rois.iterrows():

            roi_start = roi[ROI_START]
            roi_end = roi[ROI_END]

            if pd.isna(roi_start) or pd.isna(roi_end):
                continue

            total_overlap += interval_overlap(
                gt_start,
                gt_end,
                roi_start,
                roi_end
            )

        # Cap at 100%
        total_overlap = min(
            total_overlap,
            duration
        )

        coverage.append(
            total_overlap / duration
        )

    gt_analysis = gt.copy()

    gt_analysis["roi_coverage"] = coverage

    # ========================================================
    # OVERALL RESULTS
    # ========================================================

    print("\n" + "-" * 70)
    print("OVERALL ROI COVERAGE")
    print("-" * 70)

    mean_coverage = (
        gt_analysis["roi_coverage"].mean() * 100
    )

    zero_count = (
        gt_analysis["roi_coverage"] == 0
    ).sum()

    full_count = (
        gt_analysis["roi_coverage"] >= 1.0
    ).sum()

    print(
        f"Mean ROI coverage : {mean_coverage:.2f}%"
    )

    print(
        f"Zero coverage     : {zero_count:,} "
        f"({zero_count / len(gt_analysis) * 100:.2f}%)"
    )

    print(
        f"Full coverage     : {full_count:,} "
        f"({full_count / len(gt_analysis) * 100:.2f}%)"
    )

    # ========================================================
    # FREQUENCY DISTRIBUTION
    # ========================================================

    categories = [
        "Entirely below 1 kHz",
        "Crosses 1 kHz",
        "Entirely above 1 kHz",
    ]

    print("\n" + "-" * 70)
    print("GT EVENTS BY FREQUENCY CATEGORY")
    print("-" * 70)

    for category in categories:

        subset = gt_analysis[
            gt_analysis["frequency_category"] == category
        ]

        count = len(subset)

        percentage = (
            count / len(gt_analysis) * 100
        )

        print(
            f"{category:35s}: "
            f"{count:6,} "
            f"({percentage:6.2f}%)"
        )

    # ========================================================
    # COVERAGE BY FREQUENCY CATEGORY
    # ========================================================

    print("\n" + "-" * 70)
    print("ROI COVERAGE BY FREQUENCY CATEGORY")
    print("-" * 70)

    print(
        f"{'Category':35s}"
        f"{'Events':>10s}"
        f"{'Mean':>12s}"
        f"{'Zero':>12s}"
        f"{'Full':>12s}"
    )

    for category in categories:

        subset = gt_analysis[
            gt_analysis["frequency_category"] == category
        ]

        if len(subset) == 0:
            continue

        mean_cov = (
            subset["roi_coverage"].mean() * 100
        )

        zero = (
            subset["roi_coverage"] == 0
        ).sum()

        full = (
            subset["roi_coverage"] >= 1.0
        ).sum()

        print(
            f"{category:35s}"
            f"{len(subset):10,}"
            f"{mean_cov:11.2f}%"
            f"{zero:12,}"
            f"{full:12,}"
        )

    # ========================================================
    # ZERO-COVERAGE RATE
    # ========================================================

    print("\n" + "-" * 70)
    print("ZERO-COVERAGE RATE BY FREQUENCY CATEGORY")
    print("-" * 70)

    for category in categories:

        subset = gt_analysis[
            gt_analysis["frequency_category"] == category
        ]

        if len(subset) == 0:
            continue

        zero_rate = (
            (subset["roi_coverage"] == 0).mean()
            * 100
        )

        print(
            f"{category:35s}: "
            f"{zero_rate:.2f}%"
        )

    # ========================================================
    # PARTIAL COVERAGE
    # ========================================================

    print("\n" + "-" * 70)
    print("PARTIAL-COVERAGE RATE BY FREQUENCY CATEGORY")
    print("-" * 70)

    for category in categories:

        subset = gt_analysis[
            gt_analysis["frequency_category"] == category
        ]

        if len(subset) == 0:
            continue

        partial = (
            (
                (subset["roi_coverage"] > 0)
                & (subset["roi_coverage"] < 1)
            ).mean()
            * 100
        )

        print(
            f"{category:35s}: "
            f"{partial:.2f}%"
        )

    # ========================================================
    # SAVE RESULTS
    # ========================================================

    output_dir = Path(
        "evaluation_ea/results/filter_impact"
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    filename = (
        threshold_name
        .replace(" ", "_")
        .replace(".", "_")
        + ".csv"
    )

    output_file = output_dir / filename

    gt_analysis.to_csv(
        output_file,
        index=False
    )

    print(
        f"\nDetailed results saved to:\n"
        f"{output_file}"
    )


print("\n" + "=" * 70)
print("ANALYSIS COMPLETE")
print("=" * 70)