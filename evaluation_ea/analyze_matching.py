from pathlib import Path

import pandas as pd


RESULTS_DIR = Path("evaluation_ea/results")
SELECTED_DIR = RESULTS_DIR / "selected_threshold_birdnet"


CONFIGURATIONS = {
    "Raw BirdNET": {
        "predictions": RESULTS_DIR
        / "raw_birdnet_predictions.csv",
    },
    "DSP 1.00": {
        "predictions": SELECTED_DIR
        / "threshold_1_00"
        / "pipeline_birdnet_predictions.csv",
    },
    "DSP 1.25": {
        "predictions": SELECTED_DIR
        / "threshold_1_25"
        / "pipeline_birdnet_predictions.csv",
    },
}


IOU_THRESHOLDS = [
    0.00,
    0.05,
    0.10,
    0.20,
    0.30,
    0.50,
]


def load_data():

    gt = pd.read_csv(
        RESULTS_DIR / "ground_truth.csv"
    )

    predictions = {}

    for name, paths in CONFIGURATIONS.items():

        predictions[name] = pd.read_csv(
            paths["predictions"]
        )

    # Remove unknown annotations.
    gt = gt[
        gt["scientific_name"].notna()
        & (gt["scientific_name"] != "unknown")
    ].copy()

    return gt, predictions


def calculate_iou(
    gt_start,
    gt_end,
    pred_start,
    pred_end,
):

    intersection_start = max(
        gt_start,
        pred_start,
    )

    intersection_end = min(
        gt_end,
        pred_end,
    )

    intersection = max(
        0.0,
        intersection_end - intersection_start,
    )

    gt_duration = max(
        0.0,
        gt_end - gt_start,
    )

    pred_duration = max(
        0.0,
        pred_end - pred_start,
    )

    union = (
        gt_duration
        + pred_duration
        - intersection
    )

    if union <= 0:
        return 0.0

    return intersection / union


def build_candidate_pairs(
    gt,
    predictions,
):
    """
    Build candidate GT/prediction pairs.

    A candidate must:
      1. belong to the same recording
      2. have the same scientific species
      3. have positive temporal overlap
    """

    candidates = []

    for gt_index, gt_row in gt.iterrows():

        gt_filename = gt_row["filename"]
        gt_species = gt_row["scientific_name"]
        gt_start = gt_row["start_time_seconds"]
        gt_end = gt_row["end_time_seconds"]

        matching_predictions = predictions[
            (predictions["filename"] == gt_filename)
            & (
                predictions["scientific_name"]
                == gt_species
            )
        ]

        for pred_index, pred_row in (
            matching_predictions.iterrows()
        ):

            pred_start = pred_row[
                "start_time_seconds"
            ]

            pred_end = pred_row[
                "end_time_seconds"
            ]

            overlap_start = max(
                gt_start,
                pred_start,
            )

            overlap_end = min(
                gt_end,
                pred_end,
            )

            if overlap_end <= overlap_start:
                continue

            iou = calculate_iou(
                gt_start,
                gt_end,
                pred_start,
                pred_end,
            )

            confidence = (
                pred_row["confidence"]
                if "confidence" in pred_row
                else 0.0
            )

            candidates.append(
                {
                    "gt_index": gt_index,
                    "pred_index": pred_index,
                    "filename": gt_filename,
                    "scientific_name":
                        gt_species,
                    "iou": iou,
                    "confidence": confidence,
                }
            )

    return pd.DataFrame(candidates)


def greedy_match(
    candidates,
    gt,
    predictions,
    iou_threshold,
):
    """
    Greedy one-to-one matching.

    Candidate matches are considered in descending
    IoU, with confidence used as a secondary ordering.
    """

    if candidates.empty:

        tp = 0
        fp = len(predictions)
        fn = len(gt)

        return {
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "precision": 0.0,
            "recall": 0.0,
            "f1": 0.0,
        }

    eligible = candidates[
        candidates["iou"] >= iou_threshold
    ].copy()

    eligible = eligible.sort_values(
        by=["iou", "confidence"],
        ascending=[False, False],
    )

    matched_gt = set()
    matched_predictions = set()

    matches = []

    for _, candidate in eligible.iterrows():

        gt_index = candidate["gt_index"]
        pred_index = candidate["pred_index"]

        if gt_index in matched_gt:
            continue

        if pred_index in matched_predictions:
            continue

        matched_gt.add(gt_index)
        matched_predictions.add(pred_index)

        matches.append(candidate)

    tp = len(matches)

    fp = len(predictions) - tp
    fn = len(gt) - tp

    precision = (
        tp / (tp + fp)
        if tp + fp
        else 0.0
    )

    recall = (
        tp / (tp + fn)
        if tp + fn
        else 0.0
    )

    f1 = (
        2 * precision * recall
        / (precision + recall)
        if precision + recall
        else 0.0
    )

    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


def main():

    gt, predictions = load_data()

    print("=" * 80)
    print("EVENT-LEVEL BIRDNET EVALUATION")
    print("=" * 80)

    print(
        f"\nKnown ground-truth events: "
        f"{len(gt):,}"
    )

    all_results = []
    candidate_summary = []

    for name, pred_df in predictions.items():

        print("\n")
        print("=" * 80)
        print(name)
        print("=" * 80)

        print(
            f"Predictions: "
            f"{len(pred_df):,}"
        )

        print(
            "\nBuilding candidate matches..."
        )

        candidates = build_candidate_pairs(
            gt,
            pred_df,
        )

        print(
            f"Candidate pairs: "
            f"{len(candidates):,}"
        )

        candidate_summary.append(
            {
                "configuration": name,
                "ground_truth_events": len(gt),
                "predictions": len(pred_df),
                "candidate_pairs":
                    len(candidates),
            }
        )

        for threshold in IOU_THRESHOLDS:

            metrics = greedy_match(
                candidates,
                gt,
                pred_df,
                threshold,
            )

            row = {
                "configuration": name,
                "iou_threshold": threshold,
                **metrics,
            }

            all_results.append(row)

            print(
                f"\nIoU >= {threshold:.2f}"
            )

            print(
                f"  TP:        {metrics['tp']:,}"
            )

            print(
                f"  FP:        {metrics['fp']:,}"
            )

            print(
                f"  FN:        {metrics['fn']:,}"
            )

            print(
                f"  Precision: "
                f"{metrics['precision']:.4f}"
            )

            print(
                f"  Recall:    "
                f"{metrics['recall']:.4f}"
            )

            print(
                f"  F1:        "
                f"{metrics['f1']:.4f}"
            )

    # ---------------------------------------------------------
    # SAVE RESULTS
    # ---------------------------------------------------------

    results_df = pd.DataFrame(
        all_results
    )

    candidates_df = pd.DataFrame(
        candidate_summary
    )

    results_path = (
        RESULTS_DIR
        / "event_level_comparison_all.csv"
    )

    candidates_path = (
        RESULTS_DIR
        / "event_level_candidate_summary.csv"
    )

    results_df.to_csv(
        results_path,
        index=False,
    )

    candidates_df.to_csv(
        candidates_path,
        index=False,
    )

    # ---------------------------------------------------------
    # COMPACT COMPARISON
    # ---------------------------------------------------------

    print("\n")
    print("=" * 80)
    print("EVENT-LEVEL COMPARISON")
    print("=" * 80)

    display_df = results_df.copy()

    display_df["precision"] = (
        display_df["precision"]
        * 100
    )

    display_df["recall"] = (
        display_df["recall"]
        * 100
    )

    display_df["f1"] = (
        display_df["f1"]
        * 100
    )

    print(
        display_df.to_string(
            index=False,
            formatters={
                "precision":
                    "{:.2f}%".format,
                "recall":
                    "{:.2f}%".format,
                "f1":
                    "{:.2f}%".format,
            },
        )
    )

    print("\n")
    print("=" * 80)
    print("CANDIDATE PAIRS")
    print("=" * 80)

    print(
        candidates_df.to_string(
            index=False
        )
    )

    print("\nSaved:")
    print(
        f"  {results_path}"
    )

    print(
        f"  {candidates_path}"
    )


if __name__ == "__main__":
    main()

