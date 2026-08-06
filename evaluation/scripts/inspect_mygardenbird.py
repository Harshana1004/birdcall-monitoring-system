from __future__ import annotations

import csv
import wave
from collections import Counter
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]

DATASET_ROOT = (
    PROJECT_ROOT
    / "evaluation"
    / "data"
    / "mygardenbird"
    / "raw"
)

RESULTS_DIRECTORY = (
    PROJECT_ROOT
    / "evaluation"
    / "results"
)

SUPPORTED_EXTENSIONS = {
    ".wav",
}


def inspect_wav(
    path: Path,
) -> dict[str, object]:
    with wave.open(
        str(path),
        "rb",
    ) as wav_file:
        sample_rate = wav_file.getframerate()
        channels = wav_file.getnchannels()
        sample_width_bytes = wav_file.getsampwidth()
        frame_count = wav_file.getnframes()

    duration_seconds = (
        frame_count / sample_rate
        if sample_rate > 0
        else 0.0
    )

    return {
        "sample_rate": sample_rate,
        "channels": channels,
        "sample_width_bits": sample_width_bytes * 8,
        "duration_seconds": duration_seconds,
    }


def discover_audio_files() -> list[Path]:
    return sorted(
        path
        for path in DATASET_ROOT.rglob("*")
        if (
            path.is_file()
            and path.suffix.lower()
            in SUPPORTED_EXTENSIONS
        )
    )


def infer_species(
    audio_path: Path,
) -> str:
    """
    Initial assumption:

    Audio files are organized underneath a species directory.

    This will be adjusted to use official MyGardenBird metadata
    once the downloaded dataset structure is inspected.
    """

    return audio_path.parent.name


def main() -> None:
    if not DATASET_ROOT.exists():
        raise FileNotFoundError(
            "MyGardenBird dataset directory was not found at "
            f"{DATASET_ROOT}"
        )

    audio_files = discover_audio_files()

    if not audio_files:
        raise RuntimeError(
            "No WAV files were found inside "
            f"{DATASET_ROOT}"
        )

    RESULTS_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True,
    )

    species_counts: Counter[str] = Counter()
    sample_rate_counts: Counter[int] = Counter()
    channel_counts: Counter[int] = Counter()
    sample_width_counts: Counter[int] = Counter()

    durations: list[float] = []

    rows: list[dict[str, object]] = []

    for audio_path in audio_files:
        audio_info = inspect_wav(
            audio_path
        )

        species = infer_species(
            audio_path
        )

        species_counts[species] += 1

        sample_rate_counts[
            int(audio_info["sample_rate"])
        ] += 1

        channel_counts[
            int(audio_info["channels"])
        ] += 1

        sample_width_counts[
            int(audio_info["sample_width_bits"])
        ] += 1

        duration = float(
            audio_info["duration_seconds"]
        )

        durations.append(
            duration
        )

        rows.append(
            {
                "file_name": audio_path.name,
                "relative_path": str(
                    audio_path.relative_to(
                        DATASET_ROOT
                    )
                ),
                "species": species,
                **audio_info,
            }
        )

    manifest_path = (
        RESULTS_DIRECTORY
        / "mygardenbird_dataset_inventory.csv"
    )

    with manifest_path.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as output_file:
        writer = csv.DictWriter(
            output_file,
            fieldnames=[
                "file_name",
                "relative_path",
                "species",
                "sample_rate",
                "channels",
                "sample_width_bits",
                "duration_seconds",
            ],
        )

        writer.writeheader()
        writer.writerows(
            rows
        )

    print()
    print("MyGardenBird Dataset Inspection")
    print("=" * 40)

    print(
        f"Dataset directory: {DATASET_ROOT}"
    )

    print(
        f"Total WAV files: {len(audio_files)}"
    )

    print(
        f"Detected species/classes: "
        f"{len(species_counts)}"
    )

    print()
    print("Clips per species")
    print("-" * 40)

    for species, count in sorted(
        species_counts.items()
    ):
        print(
            f"{species:<35} {count:>5}"
        )

    print()
    print("Audio properties")
    print("-" * 40)

    print(
        "Sample rates:",
        dict(sample_rate_counts),
    )

    print(
        "Channels:",
        dict(channel_counts),
    )

    print(
        "Bit depths:",
        dict(sample_width_counts),
    )

    if durations:
        print(
            "Minimum duration:",
            f"{min(durations):.4f} s",
        )

        print(
            "Maximum duration:",
            f"{max(durations):.4f} s",
        )

        print(
            "Average duration:",
            f"{sum(durations) / len(durations):.4f} s",
        )

    print()
    print(
        f"Inventory written to: "
        f"{manifest_path}"
    )


if __name__ == "__main__":
    main()