import numpy as np
from scipy.signal import butter, sosfiltfilt

from pipeline.config import HIGHPASS_CUTOFF


class NoiseFilter:
    """
    Applies lightweight noise filtering to audio snippets.
    """

    def __init__(
        self,
        cutoff_frequency: float = HIGHPASS_CUTOFF,
        filter_order: int = 4,
    ) -> None:
        self.cutoff_frequency = cutoff_frequency
        self.filter_order = filter_order

    def apply_highpass_filter(
        self,
        audio: np.ndarray,
        sample_rate: int,
    ) -> np.ndarray:
        """
        Apply a Butterworth high-pass filter.

        Frequencies below cutoff_frequency are reduced.
        """

        if audio.size == 0:
            return audio

        nyquist_frequency = sample_rate / 2.0

        if self.cutoff_frequency <= 0:
            raise ValueError(
                "Cutoff frequency must be greater than zero."
            )

        if self.cutoff_frequency >= nyquist_frequency:
            raise ValueError(
                "Cutoff frequency must be below the Nyquist frequency."
            )

        normalized_cutoff = (
            self.cutoff_frequency / nyquist_frequency
        )

        second_order_sections = butter(
            N=self.filter_order,
            Wn=normalized_cutoff,
            btype="highpass",
            output="sos",
        )

        minimum_samples = 3 * (
            2 * len(second_order_sections) + 1
        )

        if len(audio) <= minimum_samples:
            print(
                "Warning: Audio snippet is too short for "
                "zero-phase filtering. Returning original snippet."
            )
            return audio.copy()

        filtered_audio = sosfiltfilt(
            second_order_sections,
            audio,
        )

        return filtered_audio.astype(np.float32)
