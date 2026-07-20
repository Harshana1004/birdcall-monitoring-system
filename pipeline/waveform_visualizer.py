from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


class WaveformVisualizer:
    """
    Creates and saves waveform and energy plots.
    """

    def plot_waveform(
        self,
        audio: np.ndarray,
        sample_rate: int,
        title: str,
        output_path: str,
    ):

        duration = len(audio) / sample_rate
        time = np.linspace(0, duration, len(audio))

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        plt.figure(figsize=(15, 4))

        plt.plot(time, audio, linewidth=0.4)

        plt.title(title)
        plt.xlabel("Time (s)")
        plt.ylabel("Normalized Amplitude")

        plt.grid(True)

        plt.tight_layout()
        plt.savefig(output_path, dpi=300)
        plt.close()

    def plot_energy(
        self,
        energy: np.ndarray,
        hop_length: int,
        sample_rate: int,
        title: str,
        output_path: str,
    ):

        time = np.arange(len(energy)) * hop_length / sample_rate

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        plt.figure(figsize=(15, 4))

        plt.plot(
            time,
            energy,
            linewidth=1,
            color="red",
        )

        plt.title(title)
        plt.xlabel("Time (s)")
        plt.ylabel("Short-Time Energy")

        plt.grid(True)

        plt.tight_layout()
        plt.savefig(output_path, dpi=300)
        plt.close()

    def plot_detected_regions(
        self,
        audio: np.ndarray,
        sample_rate: int,
        regions,
        title: str,
        output_path: str,
    ) -> None:
        duration = len(audio) / sample_rate
        time = np.arange(len(audio)) / sample_rate

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        plt.figure(figsize=(15, 5))
        plt.plot(time, audio, linewidth=0.35)

        for index, region in enumerate(regions):
            plt.axvspan(
                region.start_time,
                region.end_time,
                alpha=0.25,
                label="Detected RoI" if index == 0 else None,
            )

        plt.title(title)
        plt.xlabel("Time (s)")
        plt.ylabel("Normalized Signal Amplitude")
        plt.xlim(0, duration)
        plt.grid(True)

        if regions:
            plt.legend()

        plt.tight_layout()
        plt.savefig(output_path, dpi=300)
        plt.close()