from pathlib import Path

from pipeline.classifier import BirdNETClassifier


def main() -> None:
    input_directory = Path(
        "outputs/snippets/filtered"
    )

    output_file = Path(
        "outputs/classification_results.csv"
    )

    if not input_directory.exists():
        raise FileNotFoundError(
            f"Snippet directory not found: "
            f"{input_directory}"
        )

    audio_files = sorted(
        input_directory.glob("*.wav")
    )

    if not audio_files:
        print(
            f"No WAV files found in "
            f"{input_directory}"
        )
        return

    print(
        f"Found {len(audio_files)} "
        "filtered snippets."
    )

    classifier = BirdNETClassifier()

    print("\nRunning BirdNET classification...")

    results = classifier.classify_directory(
        input_directory
    )

    output_file.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    results.to_csv(
        output_file,
        index=False,
    )

    print("\nClassification complete.")
    print(f"Results saved to: {output_file}")

    if results.empty:
        print(
            "\nNo predictions exceeded the "
            "confidence threshold."
        )
        return

    print("\nResult columns:")
    print(list(results.columns))

    print("\nFirst predictions:")
    print(results.head(20).to_string(index=False))


if __name__ == "__main__":
    main()