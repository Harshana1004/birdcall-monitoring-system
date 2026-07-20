from pathlib import Path

from pipeline.audio_loader import AudioLoader
from pipeline.audio_normalizer import AudioNormalizer
from pipeline.noise_filter import NoiseFilter
from pipeline.roi_detector import RoIDetector
from pipeline.segmenter import Segmenter
from pipeline.utils import print_audio_info
from pipeline.waveform_visualizer import WaveformVisualizer


def main() -> None:
    print("=" * 60)
    print("BirdCall Monitoring Pipeline")
    print("=" * 60)

    input_file = Path(
        "data/test_audio/common_myna_01.wav"
    )

    raw_snippet_directory = Path(
        "outputs/snippets/raw"
    )

    filtered_snippet_directory = Path(
        "outputs/snippets/filtered"
    )

    loader = AudioLoader()
    normalizer = AudioNormalizer()
    visualizer = WaveformVisualizer()
    roi_detector = RoIDetector()
    segmenter = Segmenter()
    noise_filter = NoiseFilter()

    print("\nLoading audio...")

    audio, sample_rate = loader.load(
        str(input_file)
    )

    print("Audio loaded successfully")
    print_audio_info(audio, sample_rate)

    print("\nNormalizing audio...")

    normalized_audio = normalizer.normalize(audio)

    print("Audio normalized")

    waveform_path = Path(
        "outputs/waveforms/"
        "common_myna_01_waveform.png"
    )

    visualizer.plot_waveform(
        normalized_audio,
        sample_rate,
        "Common Myna Recording",
        str(waveform_path),
    )

    print(
        f"Waveform saved to {waveform_path}"
    )

    print("\nDetecting Regions of Interest...")

    regions, smoothed_energy, threshold = (
        roi_detector.detect_regions(
            normalized_audio
        )
    )

    print(
        f"Detection threshold: "
        f"{threshold:.8f}"
    )

    print(
        f"Detected {len(regions)} "
        "Regions of Interest"
    )

    for index, region in enumerate(
        regions,
        start=1,
    ):
        print(
            f"  RoI {index:02d}: "
            f"{region.start_time:.2f}s - "
            f"{region.end_time:.2f}s "
            f"({region.duration:.2f}s)"
        )

    energy_path = Path(
        "outputs/energy/"
        "common_myna_energy.png"
    )

    visualizer.plot_energy(
        smoothed_energy,
        roi_detector.hop_length,
        sample_rate,
        "Smoothed Short-Time Energy",
        str(energy_path),
    )

    roi_plot_path = Path(
        "outputs/roi_plots/"
        "common_myna_detected_rois.png"
    )

    visualizer.plot_detected_regions(
        normalized_audio,
        sample_rate,
        regions,
        (
            "Detected Regions of Interest "
            "– Common Myna Recording"
        ),
        str(roi_plot_path),
    )

    print(
        f"\nEnergy plot saved to "
        f"{energy_path}"
    )

    print(
        f"RoI plot saved to "
        f"{roi_plot_path}"
    )

    print("\nExtracting and filtering snippets...")

    raw_snippet_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    filtered_snippet_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    raw_files: list[Path] = []
    filtered_files: list[Path] = []

    for index, region in enumerate(
        regions,
        start=1,
    ):
        segment = segmenter.extract(
            audio=normalized_audio,
            sample_rate=sample_rate,
            region=region,
        )

        if segment.size == 0:
            print(
                f"Warning: RoI {index} produced "
                "an empty segment."
            )
            continue

        filename = segmenter.create_filename(
            prefix="common_myna",
            index=index,
            region=region,
        )

        raw_output_path = (
            raw_snippet_directory / filename
        )

        segmenter.save(
            segment=segment,
            sample_rate=sample_rate,
            output_path=raw_output_path,
        )

        raw_files.append(raw_output_path)

        filtered_segment = (
            noise_filter.apply_highpass_filter(
                audio=segment,
                sample_rate=sample_rate,
            )
        )

        filtered_output_path = (
            filtered_snippet_directory / filename
        )

        segmenter.save(
            segment=filtered_segment,
            sample_rate=sample_rate,
            output_path=filtered_output_path,
        )

        filtered_files.append(
            filtered_output_path
        )

        print(
            f"  RoI {index:02d}: "
            f"saved raw and filtered versions"
        )

    print(
        f"\nSaved {len(raw_files)} "
        "raw snippets"
    )

    print(
        f"Saved {len(filtered_files)} "
        "filtered snippets"
    )

    print(
        f"Raw snippets: "
        f"{raw_snippet_directory}"
    )

    print(
        f"Filtered snippets: "
        f"{filtered_snippet_directory}"
    )

    print("\nProcessing complete.")
    print("=" * 60)


if __name__ == "__main__":
    main()