from pathlib import Path

import librosa
import numpy as np

from pipeline.config import TARGET_SAMPLE_RATE, MONO


class AudioLoader:
    """
    Loads audio files and converts them into a standardized format.

    Responsibilities:
        - Load WAV/MP3 audio
        - Convert to mono
        - Resample to target sample rate
    """

    def __init__(
        self,
        sample_rate: int = TARGET_SAMPLE_RATE,
        mono: bool = MONO,
    ):
        self.sample_rate = sample_rate
        self.mono = mono

    def load(self, file_path: str):
        """
        Load an audio file.

        Parameters
        ----------
        file_path : str
            Path to the audio file.

        Returns
        -------
        tuple[np.ndarray, int]
            Audio samples and sample rate.
        """

        file_path = Path(file_path)

        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        audio, sr = librosa.load(
            file_path,
            sr=self.sample_rate,
            mono=self.mono,
        )

        return audio, sr


