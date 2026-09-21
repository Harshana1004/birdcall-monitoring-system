from pathlib import Path

import pandas as pd


RESULTS_DIR = Path("evaluation_ea/results")
SELECTED_DIR = RESULTS_DIR / "selected_threshold_birdnet"


THRESHOLDS = {
    "DSP 1.00": SELECTED_DIR / "threshold_1_00",
    "DSP 1.25": SELECTED_DIR / "threshold_1_25",
}


def load_data():
    """
    Load ground truth, raw BirdNET predictions,
    and selected DSP threshold results.
    """

    gt = pd.read_csv(
        RESULTS_DIR / "ground_truth.csv"
    )

    raw = pd.read_csv(
        RESULTS_DIR / "raw_birdnet_predictions.csv"
    )

    pipelines = {}

    for name, directory in THRESHOLDS.items():

        prediction_path = (
            directory / "pipeline_birdnet_predictions.csv"
        )

        roi_path = (
            directory / "pipeline_rois.csv"
        )

        pipelines[name] = {
            "predictions": pd.read_csv(prediction_path),
            "rois": pd.read_csv(roi_path),
        }

    # Remove unknown annotations from species evaluation.
    gt = gt[
        gt["scientific_name"].notna()
        & (gt["scientific_name"] != "unknown")
    ].copy()

    return gt, raw, pipelines


def recording_species(df):
    """
    Return one row per recording/species combination.
    """

    return set(
        zip(
            df["filename"],
            df["scientific_name"],
        )
    )


def species_level_metrics(gt, predictions):
    """
    Calculate recording-level species presence metrics.
    """

    gt_pairs = recording_species(gt)
    prediction_pairs = recording_species(
        predictions
    )

    tp_pairs = gt_pairs & prediction_pairs
    fp_pairs = prediction_pairs - gt_pairs
    fn_pairs = gt_pairs - prediction_pairs

    tp = len(tp_pairs)
    fp = len(fp_pairs)
    fn = len(fn_pairs)

    precision = (
        tp / (tp + fp)
        if tp + fp
        else 0
    )

    recall = (
        tp / (tp + fn)
        if tp + fn
        else 0
    )

    f1 = (
        2 * precision * recall
        / (precision + recall)
        if precision + recall
        else 0
    )

    return {
        "ground_truth_recording_species":
            len(gt_pairs),
        "predicted_recording_species":
            len(prediction_pairs),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


def species_presence_table(
    gt,
    raw,
    pipelines,
):
    """
    Create a recording/species presence table
    for raw BirdNET and all selected DSP thresholds.
    """

    gt_pairs = recording_species(gt)
    raw_pairs = recording_species(raw)

    pipeline_pairs = {
        name: recording_species(
            data["predictions"]
        )
        for name, data in pipelines.items()
    }

    all_pairs = set(gt_pairs) | raw_pairs

    for pairs in pipeline_pairs.values():
        all_pairs |= pairs

    all_pairs = sorted(all_pairs)

    rows = []

    for filename, species in all_pairs:

        row = {
            "filename": filename,
            "scientific_name": species,
            "ground_truth_present":
                (filename, species) in gt_pairs,
            "raw_detected":
                (filename, species) in raw_pairs,
        }

        for name, pairs in pipeline_pairs.items():

            column_name = (
                name.lower()
                .replace(" ", "_")
                .replace(".", "")
            )

            row[
                f"{column_name}_detected"
            ] = (
                filename,
                species
            ) in pairs

        rows.append(row)

    return pd.DataFrame(rows)


def calculate_roi_temporal_coverage(
    gt,
    rois,
):
    """
    Calculate the fraction of each ground-truth
    event covered by DSP ROIs.
    """

    results = []

    for _, event in gt.iterrows():

        event_start = (
            event["start_time_seconds"]
        )

        event_end = (
            event["end_time_seconds"]
        )

        event_duration = (
            event_end - event_start
        )

        matching_rois = rois[
            rois["filename"]
            == event["filename"]
        ]

        intervals = []

        for _, roi in matching_rois.iterrows():

            start = max(
                event_start,
                roi["roi_start_seconds"],
            )

            end = min(
                event_end,
                roi["roi_end_seconds"],
            )

            if end > start:
                intervals.append(
                    (start, end)
                )

        # Merge overlapping ROI intervals.
        intervals.sort()

        merged = []

        for start, end in intervals:

            if (
                not merged
                or start > merged[-1][1]
            ):
                merged.append(
                    [start, end]
                )
            else:
                merged[-1][1] = max(
                    merged[-1][1],
                    end,
                )

        covered_duration = sum(
            end - start
            for start, end in merged
        )

        if event_duration > 0:

            coverage = min(
                covered_duration
                / event_duration,
                1.0,
            )

        else:

            coverage = None

        results.append(
            {
                "ground_truth_id":
                    event["ground_truth_id"],
                "filename":
                    event["filename"],
                "scientific_name":
                    event["scientific_name"],
                "duration_seconds":
                    event_duration,
                "covered_seconds":
                    covered_duration,
                "coverage":
                    coverage,
            }
        )

    return pd.DataFrame(results)


def print_species_metrics(
    name,
    metrics,
):
    """
    Print species-level metrics in a consistent format.
    """

    print(f"\n{name}")

    for key, value in metrics.items():

        if isinstance(value, float):

            print(
                f"{key}: {value:.4f}"
            )

        else:

            print(
                f"{key}: {value:,}"
            )


def calculate_unique_species(
    gt,
    raw,
    pipelines,
):
    """
    Calculate unique species detected/recovered.
    """

    gt_species = set(
        gt["scientific_name"]
    )

    raw_species = set(
        raw["scientific_name"]
    )

    print("\n")
    print("=" * 75)
    print("UNIQUE SPECIES")
    print("=" * 75)

    print(
        f"Ground-truth species: "
        f"{len(gt_species)}"
    )

    print(
        f"Raw BirdNET species:  "
        f"{len(raw_species)}"
    )

    print(
        f"Raw species recovered: "
        f"{len(gt_species & raw_species)}"
    )

    rows = []

    for name, data in pipelines.items():

        species = set(
            data["predictions"][
                "scientific_name"
            ]
        )

        recovered = (
            gt_species & species
        )

        print(
            f"{name} species:     "
            f"{len(species)}"
        )

        print(
            f"{name} recovered:   "
            f"{len(recovered)}"
        )

        rows.append(
            {
                "configuration": name,
                "predicted_species":
                    len(species),
                "ground_truth_species_recovered":
                    len(recovered),
            }
        )

    return pd.DataFrame(rows)


def calculate_coverage_summary(
    gt,
    pipelines,
):
    """
    Calculate ROI temporal coverage for each
    DSP threshold.
    """

    print("\n")
    print("=" * 75)
    print("ROI TEMPORAL COVERAGE")
    print("=" * 75)

    summary_rows = []

    for name, data in pipelines.items():

        print(f"\n{name}")

        coverage = (
            calculate_roi_temporal_coverage(
                gt,
                data["rois"],
            )
        )

        valid_coverage = coverage[
            coverage["coverage"].notna()
        ]

        print(
            f"Events with measurable duration: "
            f"{len(valid_coverage):,}"
        )

        print("\nCoverage statistics:")

        print(
            valid_coverage[
                "coverage"
            ]
            .describe()
            .to_string()
        )

        print("\nCoverage buckets:")

        buckets = pd.cut(
            valid_coverage["coverage"],
            bins=[
                -0.001,
                0.0,
                0.25,
                0.50,
                0.75,
                0.999999,
                1.0,
            ],
            labels=[
                "0%",
                ">0–25%",
                "25–50%",
                "50–75%",
                "75–<100%",
                "100%",
            ],
        )

        bucket_counts = (
            buckets
            .value_counts(sort=False)
        )

        print(
            bucket_counts.to_string()
        )

        coverage.to_csv(
            RESULTS_DIR
            / f"roi_temporal_coverage_"
              f"{name.lower().replace(' ', '_').replace('.', '')}.csv",
            index=False,
        )

        summary_rows.append(
            {
                "configuration": name,
                "measurable_events":
                    len(valid_coverage),
                "mean_coverage":
                    valid_coverage[
                        "coverage"
                    ].mean(),
                "median_coverage":
                    valid_coverage[
                        "coverage"
                    ].median(),
                "zero_coverage_events":
                    int(
                        (
                            valid_coverage[
                                "coverage"
                            ] == 0
                        ).sum()
                    ),
                "full_coverage_events":
                    int(
                        (
                            valid_coverage[
                                "coverage"
                            ] == 1
                        ).sum()
                    ),
            }
        )

    return pd.DataFrame(summary_rows)


def main():

    gt, raw, pipelines = load_data()

    print("=" * 75)
    print(
        "RECORDING-LEVEL SPECIES EVALUATION"
    )
    print("=" * 75)

    print(
        f"\nGround-truth events after "
        f"removing unknown species: "
        f"{len(gt):,}"
    )

    # ---------------------------------------------------------
    # SPECIES-LEVEL METRICS
    # ---------------------------------------------------------

    metrics_rows = []

    raw_metrics = species_level_metrics(
        gt,
        raw,
    )

    print_species_metrics(
        "RAW BIRDNET",
        raw_metrics,
    )

    metrics_rows.append(
        {
            "configuration": "Raw BirdNET",
            **raw_metrics,
        }
    )

    for name, data in pipelines.items():

        metrics = species_level_metrics(
            gt,
            data["predictions"],
        )

        print_species_metrics(
            name,
            metrics,
        )

        metrics_rows.append(
            {
                "configuration": name,
                **metrics,
            }
        )

    comparison = pd.DataFrame(
        metrics_rows
    )

    print("\n")
    print("=" * 75)
    print("SPECIES-LEVEL COMPARISON")
    print("=" * 75)

    print(
        comparison.to_string(
            index=False
        )
    )

    comparison.to_csv(
        RESULTS_DIR
        / "species_level_comparison_all.csv",
        index=False,
    )

    # ---------------------------------------------------------
    # SPECIES PRESENCE
    # ---------------------------------------------------------

    presence = species_presence_table(
        gt,
        raw,
        pipelines,
    )

    presence.to_csv(
        RESULTS_DIR
        / "species_presence_all.csv",
        index=False,
    )

    # ---------------------------------------------------------
    # UNIQUE SPECIES
    # ---------------------------------------------------------

    unique_species = calculate_unique_species(
        gt,
        raw,
        pipelines,
    )

    unique_species.to_csv(
        RESULTS_DIR
        / "unique_species_comparison.csv",
        index=False,
    )

    # ---------------------------------------------------------
    # ROI TEMPORAL COVERAGE
    # ---------------------------------------------------------

    coverage_summary = (
        calculate_coverage_summary(
            gt,
            pipelines,
        )
    )

    coverage_summary.to_csv(
        RESULTS_DIR
        / "roi_coverage_summary_all.csv",
        index=False,
    )

    # ---------------------------------------------------------
    # FINAL SUMMARY
    # ---------------------------------------------------------

    print("\n")
    print("=" * 75)
    print("FILES SAVED")
    print("=" * 75)

    print(
        "  evaluation_ea/results/"
        "species_level_comparison_all.csv"
    )

    print(
        "  evaluation_ea/results/"
        "species_presence_all.csv"
    )

    print(
        "  evaluation_ea/results/"
        "unique_species_comparison.csv"
    )

    print(
        "  evaluation_ea/results/"
        "roi_coverage_summary_all.csv"
    )

    print(
        "\nDone."
    )


if __name__ == "__main__":
    main()