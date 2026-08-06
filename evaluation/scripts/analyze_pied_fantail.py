from pathlib import Path

import pandas as pd


RESULTS_DIR = Path("evaluation/results")
PREDICTIONS_DIR = Path("evaluation/predictions")

CLIP_RESULTS_PATH = (
    RESULTS_DIR / "e0_clip_results_full.csv"
)

PREDICTIONS_PATH = (
    PREDICTIONS_DIR / "e0_predictions_full.csv"
)

TARGET_SPECIES = "Pied Fantail"


def main() -> None:
    print("=" * 70)
    print("E0.1 - Pied Fantail Failure Analysis")
    print("=" * 70)

    clips = pd.read_csv(CLIP_RESULTS_PATH)
    predictions = pd.read_csv(PREDICTIONS_PATH)

    target_clips = clips[
        clips["true_species"] == TARGET_SPECIES
    ].copy()

    target_predictions = predictions[
        predictions["true_species"] == TARGET_SPECIES
    ].copy()

    total = len(target_clips)

    if total == 0:
        raise RuntimeError(
            f"No clips found for {TARGET_SPECIES}."
        )

    print(f"\nGround-truth species: {TARGET_SPECIES}")
    print(f"Total clips: {total}")

    # ---------------------------------------------------------
    # E0 classification behaviour
    # ---------------------------------------------------------

    correct = int(
        target_clips["correct_top1"].sum()
    )

    abstentions = int(
        (
            target_clips["mapped_prediction"]
            == "__ABSTAIN__"
        ).sum()
    )

    outside = int(
        (
            target_clips["mapped_prediction"]
            == "__OTHER__"
        ).sum()
    )

    print("\nClassification behaviour")
    print("-" * 70)

    print(
        f"Correct Top-1: {correct}/{total} "
        f"({correct / total:.2%})"
    )

    print(
        f"Abstentions: {abstentions}/{total} "
        f"({abstentions / total:.2%})"
    )

    print(
        f"Outside-dataset predictions: {outside}/{total} "
        f"({outside / total:.2%})"
    )

    # ---------------------------------------------------------
    # Predictions returned by BirdNET
    # ---------------------------------------------------------

    print("\nReturned BirdNET predictions")
    print("-" * 70)

    print(
        f"Total prediction rows: "
        f"{len(target_predictions)}"
    )

    clips_with_predictions = (
        target_predictions["file_name"].nunique()
    )

    print(
        f"Clips with >=1 prediction: "
        f"{clips_with_predictions}/{total} "
        f"({clips_with_predictions / total:.2%})"
    )

    # ---------------------------------------------------------
    # Rank distribution
    # ---------------------------------------------------------

    if not target_predictions.empty:
        print("\nPrediction rank distribution")
        print("-" * 70)

        print(
            target_predictions["rank"]
            .value_counts()
            .sort_index()
            .to_string()
        )

    # ---------------------------------------------------------
    # Most frequent common-name predictions
    # ---------------------------------------------------------

    print("\nMost frequent predicted common names")
    print("-" * 70)

    if target_predictions.empty:
        print("No predictions were returned.")

    else:
        common_counts = (
            target_predictions["common_name"]
            .fillna("<missing>")
            .value_counts()
            .head(20)
        )

        print(common_counts.to_string())

    # ---------------------------------------------------------
    # Most frequent scientific-name predictions
    # ---------------------------------------------------------

    print("\nMost frequent predicted scientific names")
    print("-" * 70)

    if target_predictions.empty:
        print("No predictions were returned.")

    else:
        scientific_counts = (
            target_predictions["scientific_name"]
            .fillna("<missing>")
            .value_counts()
            .head(20)
        )

        print(scientific_counts.to_string())

    # ---------------------------------------------------------
    # Search explicitly for anything containing Fantail
    # ---------------------------------------------------------

    print("\nPredictions containing 'fantail'")
    print("-" * 70)

    if target_predictions.empty:
        fantail_predictions = (
            target_predictions.copy()
        )

    else:
        common_match = (
            target_predictions["common_name"]
            .fillna("")
            .str.contains(
                "fantail",
                case=False,
                regex=False,
            )
        )

        scientific_match = (
            target_predictions["scientific_name"]
            .fillna("")
            .str.contains(
                "fantail",
                case=False,
                regex=False,
            )
        )

        fantail_predictions = target_predictions[
            common_match | scientific_match
        ]

    if fantail_predictions.empty:
        print(
            "BirdNET returned no prediction containing "
            "'fantail' at the current confidence threshold."
        )

    else:
        print(
            fantail_predictions[
                [
                    "file_name",
                    "rank",
                    "scientific_name",
                    "common_name",
                    "confidence",
                ]
            ]
            .sort_values(
                "confidence",
                ascending=False,
            )
            .head(30)
            .to_string(index=False)
        )

    # ---------------------------------------------------------
    # Confidence statistics
    # ---------------------------------------------------------

    print("\nConfidence statistics")
    print("-" * 70)

    non_abstaining = target_clips[
        target_clips["mapped_prediction"]
        != "__ABSTAIN__"
    ]

    if non_abstaining.empty:
        print(
            "No non-abstaining predictions available."
        )

    else:
        confidence = (
            non_abstaining["confidence"]
        )

        print(
            f"Mean Top-1 confidence: "
            f"{confidence.mean():.4f}"
        )

        print(
            f"Median Top-1 confidence: "
            f"{confidence.median():.4f}"
        )

        print(
            f"Minimum Top-1 confidence: "
            f"{confidence.min():.4f}"
        )

        print(
            f"Maximum Top-1 confidence: "
            f"{confidence.max():.4f}"
        )

    # ---------------------------------------------------------
    # Highest-confidence mistakes
    # ---------------------------------------------------------

    print("\nHighest-confidence predictions")
    print("-" * 70)

    highest = (
        target_clips[
            target_clips["mapped_prediction"]
            != "__ABSTAIN__"
        ]
        .sort_values(
            "confidence",
            ascending=False,
        )
        .head(20)
    )

    if highest.empty:
        print("No predictions available.")

    else:
        print(
            highest[
                [
                    "file_name",
                    "predicted_scientific_name",
                    "predicted_common_name",
                    "mapped_prediction",
                    "confidence",
                ]
            ].to_string(index=False)
        )

    # ---------------------------------------------------------
    # Save detailed analysis
    # ---------------------------------------------------------

    output_path = (
        RESULTS_DIR
        / "e0_pied_fantail_analysis.csv"
    )

    target_clips.to_csv(
        output_path,
        index=False,
    )

    print("\nGenerated file")
    print("-" * 70)
    print(output_path)

    print("\n" + "=" * 70)
    print("E0.1 analysis complete.")
    print("=" * 70)


if __name__ == "__main__":
    main()