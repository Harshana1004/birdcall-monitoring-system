from pathlib import Path

import birdnet
import pandas as pd

from pipeline.config import (
    BIRDNET_MIN_CONFIDENCE,
    BIRDNET_TOP_K,
)


class BirdNETClassifier:
    """
    Server-side BirdNET V2.4 classifier.

    The model is loaded once and reused for all audio files.
    """

    def __init__(
        self,
        minimum_confidence: float = BIRDNET_MIN_CONFIDENCE,
        top_k: int = BIRDNET_TOP_K,
    ) -> None:
        if not 0.0 <= minimum_confidence <= 1.0:
            raise ValueError(
                "minimum_confidence must be between 0 and 1."
            )

        if top_k <= 0:
            raise ValueError(
                "top_k must be greater than zero."
            )

        self.minimum_confidence = minimum_confidence
        self.top_k = top_k

        print("Loading BirdNET V2.4 model...")

        self.model = birdnet.load(
            "acoustic",
            "2.4",
            "tf",
        )

        print("BirdNET model loaded successfully.")

    def classify_file(
        self,
        audio_path: str | Path,
    ) -> pd.DataFrame:
        """
        Classify one audio file and return predictions
        as a Pandas DataFrame.
        """

        audio_path = Path(audio_path)

        if not audio_path.exists():
            raise FileNotFoundError(
                f"Audio file not found: {audio_path}"
            )

        predictions = self.model.predict(
            audio_path,
            top_k=self.top_k,
            default_confidence_threshold=(
                self.minimum_confidence
            ),
        )

        return predictions.to_dataframe()

    def classify_directory(
        self,
        input_directory: str | Path,
    ) -> pd.DataFrame:
        """
        Classify every supported audio file in a directory.
        """

        input_directory = Path(input_directory)

        if not input_directory.exists():
            raise FileNotFoundError(
                f"Directory not found: {input_directory}"
            )

        predictions = self.model.predict(
            input_directory,
            top_k=self.top_k,
            default_confidence_threshold=(
                self.minimum_confidence
            ),
        )

        return predictions.to_dataframe()