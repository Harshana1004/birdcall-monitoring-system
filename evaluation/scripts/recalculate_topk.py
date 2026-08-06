from pathlib import Path

import pandas as pd


PREDICTIONS_PATH = Path(
    "evaluation/predictions/e0_predictions_full.csv"
)

CLIP_RESULTS_PATH = Path(
    "evaluation/results/e0_clip_results_full.csv"
)


def normalize_species_name(
    value: str,
) -> str:
    return " ".join(
        value.strip()
        .lower()
        .replace("-", " ")
        .replace("_", " ")
        .split()
    )


def map_prediction_to_dataset_class(
    *,
    common_name: str,
    scientific_name: str,
) -> str:
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

    # MyGardenBird uses "Pied Fantail",
    # while BirdNET uses "Malaysian Pied-Fantail"
    # for Rhipidura javanica.
    if (
        normalized_common_name
        in {
            "pied fantail",
            "malaysian pied fantail",
        }
        or normalized_scientific_name
        == "rhipidura javanica"
    ):
        return "Pied Fantail"

    return common_name.strip()


def main() -> None:
    predictions = pd.read_csv(
        PREDICTIONS_PATH
    )

    clips = pd.read_csv(
        CLIP_RESULTS_PATH
    )

    predictions_by_file = {
        file_name: group.sort_values(
            "rank"
        )
        for file_name, group
        in predictions.groupby(
            "file_name"
        )
    }

    total_clips = len(
        clips
    )

    top1_correct = 0
    top3_correct = 0
    top5_correct = 0

    for _, clip in clips.iterrows():
        file_name = str(
            clip["file_name"]
        )

        true_species = str(
            clip["true_species"]
        ).strip()

        file_predictions = (
            predictions_by_file.get(
                file_name
            )
        )

        if file_predictions is None:
            continue

        mapped_predictions = []

        for _, prediction in (
            file_predictions.iterrows()
        ):
            mapped_species = (
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
                )
            )

            mapped_predictions.append(
                mapped_species
            )

        if (
            true_species
            in mapped_predictions[:1]
        ):
            top1_correct += 1

        if (
            true_species
            in mapped_predictions[:3]
        ):
            top3_correct += 1

        if (
            true_species
            in mapped_predictions[:5]
        ):
            top5_correct += 1

    top1_accuracy = (
        top1_correct
        / total_clips
    )

    top3_accuracy = (
        top3_correct
        / total_clips
    )

    top5_accuracy = (
        top5_correct
        / total_clips
    )

    print()
    print("=" * 60)
    print(
        "Corrected E0 Top-K Results"
    )
    print("=" * 60)

    print(
        f"Evaluated clips: "
        f"{total_clips}"
    )

    print()

    print(
        f"Top-1 correct: "
        f"{top1_correct}/"
        f"{total_clips}"
    )

    print(
        f"Top-1 accuracy: "
        f"{top1_accuracy:.4f}"
    )

    print()

    print(
        f"Top-3 correct: "
        f"{top3_correct}/"
        f"{total_clips}"
    )

    print(
        f"Top-3 accuracy: "
        f"{top3_accuracy:.4f}"
    )

    print()

    print(
        f"Top-5 correct: "
        f"{top5_correct}/"
        f"{total_clips}"
    )

    print(
        f"Top-5 accuracy: "
        f"{top5_accuracy:.4f}"
    )

    print()

    if (
        top1_accuracy
        <= top3_accuracy
        <= top5_accuracy
    ):
        print(
            "Top-K consistency check: PASS"
        )

        print(
            "Top-1 <= Top-3 <= Top-5"
        )

    else:
        print(
            "Top-K consistency check: FAIL"
        )


if __name__ == "__main__":
    main()