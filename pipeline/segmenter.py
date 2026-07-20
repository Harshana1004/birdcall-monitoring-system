# from pathlib import Path

# import numpy as np
# import soundfile as sf

# from pipeline.config import BIRDNET_MIN_DURATION
# from pipeline.roi_detector import RegionOfInterest


# class Segmenter:
#     """
#     Extracts the exact detected Region of Interest.

#     RoIs shorter than BirdNET's minimum duration are centred
#     within a fixed-length segment using silence padding.

#     Separate RoIs are not combined, and no surrounding audio
#     is taken from the original recording.
#     """

#     def __init__(
#         self,
#         target_duration: float = BIRDNET_MIN_DURATION,
#     ) -> None:
#         if target_duration <= 0:
#             raise ValueError(
#                 "target_duration must be greater than zero."
#             )

#         self.target_duration = target_duration

#     def extract(
#         self,
#         audio: np.ndarray,
#         sample_rate: int,
#         region: RegionOfInterest,
#     ) -> np.ndarray:
#         """
#         Extract the exact RoI and fit it to the target duration.

#         Short RoIs are padded equally with silence before and after.

#         Example:

#             Original RoI duration: 1 second
#             Target duration: 3 seconds

#             Output:
#             1 second silence
#             + 1 second RoI
#             + 1 second silence
#         """

#         if sample_rate <= 0:
#             raise ValueError(
#                 "sample_rate must be greater than zero."
#             )

#         if audio.size == 0:
#             return np.array(
#                 [],
#                 dtype=audio.dtype,
#             )

#         start_sample = int(
#             region.start_time * sample_rate
#         )

#         end_sample = int(
#             region.end_time * sample_rate
#         )

#         # Keep sample positions inside the recording.
#         start_sample = max(
#             0,
#             start_sample,
#         )

#         end_sample = min(
#             len(audio),
#             end_sample,
#         )

#         if end_sample <= start_sample:
#             return np.array(
#                 [],
#                 dtype=audio.dtype,
#             )

#         # Extract only the exact detected RoI.
#         segment = audio[
#             start_sample:end_sample
#         ].copy()

#         return self._fit_to_target_duration(
#             segment=segment,
#             sample_rate=sample_rate,
#         )

#     def _fit_to_target_duration(
#         self,
#         segment: np.ndarray,
#         sample_rate: int,
#     ) -> np.ndarray:
#         """
#         Pad short segments with silence to reach the target duration.

#         Segments longer than the target duration are centre-cropped.
#         """

#         target_samples = int(
#             round(
#                 self.target_duration * sample_rate
#             )
#         )

#         current_samples = len(segment)

#         if current_samples == target_samples:
#             return segment.copy()

#         if current_samples < target_samples:
#             missing_samples = (
#                 target_samples - current_samples
#             )

#             padding_before = (
#                 missing_samples // 2
#             )

#             padding_after = (
#                 missing_samples - padding_before
#             )

#             padded_segment = np.pad(
#                 segment,
#                 pad_width=(
#                     padding_before,
#                     padding_after,
#                 ),
#                 mode="constant",
#                 constant_values=0,
#             )

#             return padded_segment.astype(
#                 segment.dtype,
#                 copy=False,
#             )

#         # If an RoI is longer than the target duration,
#         # keep its central portion.
#         excess_samples = (
#             current_samples - target_samples
#         )

#         crop_before = (
#             excess_samples // 2
#         )

#         crop_after = (
#             crop_before + target_samples
#         )

#         return segment[
#             crop_before:crop_after
#         ].copy()

#     def save(
#         self,
#         segment: np.ndarray,
#         sample_rate: int,
#         output_path: str | Path,
#     ) -> Path:
#         """
#         Save the extracted segment as a 16-bit PCM WAV file.
#         """

#         if segment.size == 0:
#             raise ValueError(
#                 "Cannot save an empty audio segment."
#             )

#         output_path = Path(output_path)

#         output_path.parent.mkdir(
#             parents=True,
#             exist_ok=True,
#         )

#         sf.write(
#             output_path,
#             segment,
#             sample_rate,
#             subtype="PCM_16",
#         )

#         return output_path

#     def create_filename(
#         self,
#         prefix: str,
#         index: int,
#         region: RegionOfInterest,
#     ) -> str:
#         """
#         Create a filename using the original RoI times.

#         The times in the filename represent the detected RoI,
#         not the silence-padded output duration.
#         """

#         return (
#             f"{prefix}_{index:03d}_"
#             f"{region.start_time:.2f}s-"
#             f"{region.end_time:.2f}s.wav"
#         )

from pathlib import Path

import numpy as np
import soundfile as sf

from pipeline.config import BIRDNET_MIN_DURATION
from pipeline.roi_detector import RegionOfInterest


class Segmenter:
    """
    Extracts the exact detected Region of Interest.

    RoIs shorter than BirdNET's minimum duration are
    centre-padded with silence.

    RoIs equal to or longer than the minimum duration
    are kept unchanged.

    No surrounding audio is added, and long RoIs are
    never cropped.
    """

    def __init__(
        self,
        minimum_duration: float = BIRDNET_MIN_DURATION,
    ) -> None:
        if minimum_duration <= 0:
            raise ValueError(
                "minimum_duration must be greater than zero."
            )

        self.minimum_duration = minimum_duration

    def extract(
        self,
        audio: np.ndarray,
        sample_rate: int,
        region: RegionOfInterest,
    ) -> np.ndarray:
        """
        Extract the exact RoI.

        Short RoIs are padded with silence to reach the
        configured minimum duration.

        Long RoIs are returned unchanged so BirdNET can
        process them using its internal analysis windows.
        """

        if sample_rate <= 0:
            raise ValueError(
                "sample_rate must be greater than zero."
            )

        if audio.size == 0:
            return np.array(
                [],
                dtype=audio.dtype,
            )

        start_sample = int(
            round(region.start_time * sample_rate)
        )

        end_sample = int(
            round(region.end_time * sample_rate)
        )

        start_sample = max(
            0,
            start_sample,
        )

        end_sample = min(
            len(audio),
            end_sample,
        )

        if end_sample <= start_sample:
            return np.array(
                [],
                dtype=audio.dtype,
            )

        # Extract only the detected RoI.
        segment = audio[
            start_sample:end_sample
        ].copy()

        return self._pad_to_minimum_duration(
            segment=segment,
            sample_rate=sample_rate,
        )

    def _pad_to_minimum_duration(
        self,
        segment: np.ndarray,
        sample_rate: int,
    ) -> np.ndarray:
        """
        Pad segments shorter than the minimum duration.

        Segments already meeting or exceeding the minimum
        duration are returned without cropping.
        """

        minimum_samples = int(
            round(
                self.minimum_duration * sample_rate
            )
        )

        current_samples = len(segment)

        if current_samples >= minimum_samples:
            return segment.copy()

        missing_samples = (
            minimum_samples - current_samples
        )

        padding_before = (
            missing_samples // 2
        )

        padding_after = (
            missing_samples - padding_before
        )

        padded_segment = np.pad(
            segment,
            pad_width=(
                padding_before,
                padding_after,
            ),
            mode="constant",
            constant_values=0,
        )

        return padded_segment.astype(
            segment.dtype,
            copy=False,
        )

    def save(
        self,
        segment: np.ndarray,
        sample_rate: int,
        output_path: str | Path,
    ) -> Path:
        """
        Save the audio segment as a 16-bit PCM WAV file.
        """

        if segment.size == 0:
            raise ValueError(
                "Cannot save an empty audio segment."
            )

        output_path = Path(output_path)

        output_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        sf.write(
            output_path,
            segment,
            sample_rate,
            subtype="PCM_16",
        )

        return output_path

    def create_filename(
        self,
        prefix: str,
        index: int,
        region: RegionOfInterest,
    ) -> str:
        """
        Create a filename using the original RoI timestamps.
        """

        return (
            f"{prefix}_{index:03d}_"
            f"{region.start_time:.2f}s-"
            f"{region.end_time:.2f}s.wav"
        )