import sys
from pathlib import Path

import numpy as np

from src.services.audio_processing import (
    AudioProcessingService,
)


def main() -> None:
    if len(
        sys.argv
    ) != 2:
        print(
            "Usage:"
        )

        print(
            "python -m tests.test_audio_processing "
            "\"path/to/audio.wav\""
        )

        raise SystemExit(
            1
        )

    audio_path = Path(
        sys.argv[1]
    )

    service = (
        AudioProcessingService()
    )

    result = (
        service.process(
            audio_path
        )
    )

    print()
    print(
        "=" * 60
    )

    print(
        "Manual Audio Processing Test"
    )

    print(
        "=" * 60
    )

    print(
        f"File: "
        f"{result.original_filename}"
    )

    print(
        f"Sample rate: "
        f"{result.sample_rate} Hz"
    )

    print(
        f"Duration: "
        f"{result.duration_seconds:.3f} s"
    )

    print(
        f"Normalized peak: "
        f"{np.max(np.abs(result.normalized_audio)):.4f}"
    )

    print(
        f"Energy frames: "
        f"{len(result.energy)}"
    )

    print(
        f"Energy threshold: "
        f"{result.energy_threshold:.8f}"
    )

    print(
        f"Detected ROIs: "
        f"{len(result.rois)}"
    )

    print()

    for roi in result.rois:
        final_duration = (
            len(
                roi.audio
            )
            / result.sample_rate
        )

        print(
            f"ROI {roi.index}"
        )

        print(
            f"  Original interval: "
            f"{roi.region.start_time:.3f} "
            f"- "
            f"{roi.region.end_time:.3f} s"
        )

        print(
            f"  Original ROI duration: "
            f"{roi.original_duration_seconds:.3f} s"
        )

        print(
            f"  BirdNET-ready duration: "
            f"{final_duration:.3f} s"
        )

        print(
            f"  Samples: "
            f"{len(roi.audio)}"
        )

        print()

    print(
        "Audio processing test: PASS"
    )


if __name__ == "__main__":
    main()