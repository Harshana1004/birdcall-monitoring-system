import numpy as np


class AudioNormalizer:
    """
    Normalize audio amplitude to the range [-1, 1].
    """

    def normalize(self, audio: np.ndarray) -> np.ndarray:

        peak = np.max(np.abs(audio))

        if peak == 0:
            return audio

        return audio / peak