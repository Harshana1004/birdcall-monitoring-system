from dataclasses import dataclass

import numpy as np

from pipeline.config import (
    FRAME_DURATION,
    HOP_DURATION,
    ROI_MERGE_GAP,
    ROI_MIN_DURATION,
    ROI_PADDING,
    ROI_THRESHOLD_FACTOR,
    TARGET_SAMPLE_RATE,
)


@dataclass
class RegionOfInterest:
    """
    Represents a detected acoustic region in seconds.
    """

    start_time: float
    end_time: float

    @property
    def duration(self) -> float:
        return self.end_time - self.start_time


class RoIDetector:
    """
    Detects possible acoustic events using short-time energy.
    """

    def __init__(
        self,
        sample_rate: int = TARGET_SAMPLE_RATE,
    ) -> None:
        self.sample_rate = sample_rate
        self.frame_length = int(FRAME_DURATION * sample_rate)
        self.hop_length = int(HOP_DURATION * sample_rate)

    def compute_short_time_energy(
        self,
        audio: np.ndarray,
    ) -> np.ndarray:
        """
        Calculate mean squared energy for overlapping audio frames.
        """

        if audio.size < self.frame_length:
            return np.array([], dtype=np.float32)

        energy_values: list[float] = []

        for start in range(
            0,
            len(audio) - self.frame_length + 1,
            self.hop_length,
        ):
            frame = audio[start : start + self.frame_length]
            frame_energy = float(np.mean(frame**2))
            energy_values.append(frame_energy)

        return np.asarray(energy_values, dtype=np.float32)

    def smooth_energy(
        self,
        energy: np.ndarray,
        window_size: int = 15,
    ) -> np.ndarray:
        """
        Smooth the energy curve using a moving average.
        """

        if energy.size == 0:
            return energy

        window_size = max(1, min(window_size, len(energy)))
        kernel = np.ones(window_size, dtype=np.float32) / window_size

        return np.convolve(energy, kernel, mode="same")

    def calculate_threshold(
        self,
        smoothed_energy: np.ndarray,
    ) -> float:
        """
        Calculate an adaptive threshold using the median energy.
        """

        if smoothed_energy.size == 0:
            return 0.0

        median_energy = float(np.median(smoothed_energy))
        threshold = median_energy * ROI_THRESHOLD_FACTOR

        return threshold

    def detect_regions(
        self,
        audio: np.ndarray,
    ) -> tuple[list[RegionOfInterest], np.ndarray, float]:
        """
        Detect and merge active acoustic regions.

        Returns
        -------
        regions:
            Detected start and end times.
        smoothed_energy:
            Energy envelope used for detection.
        threshold:
            Adaptive threshold used for classification.
        """

        energy = self.compute_short_time_energy(audio)
        smoothed_energy = self.smooth_energy(energy)
        threshold = self.calculate_threshold(smoothed_energy)

        if smoothed_energy.size == 0:
            return [], smoothed_energy, threshold

        active_frames = smoothed_energy >= threshold
        raw_regions = self._active_frames_to_regions(active_frames)
        merged_regions = self._merge_regions(raw_regions)
        filtered_regions = self._filter_and_pad_regions(
            merged_regions,
            audio_duration=len(audio) / self.sample_rate,
        )

        return filtered_regions, smoothed_energy, threshold

    def _active_frames_to_regions(
        self,
        active_frames: np.ndarray,
    ) -> list[RegionOfInterest]:
        regions: list[RegionOfInterest] = []
        start_frame: int | None = None

        for index, is_active in enumerate(active_frames):
            if is_active and start_frame is None:
                start_frame = index

            if not is_active and start_frame is not None:
                regions.append(
                    self._frames_to_region(start_frame, index - 1)
                )
                start_frame = None

        if start_frame is not None:
            regions.append(
                self._frames_to_region(
                    start_frame,
                    len(active_frames) - 1,
                )
            )

        return regions

    def _frames_to_region(
        self,
        start_frame: int,
        end_frame: int,
    ) -> RegionOfInterest:
        start_time = start_frame * self.hop_length / self.sample_rate

        end_time = (
            end_frame * self.hop_length + self.frame_length
        ) / self.sample_rate

        return RegionOfInterest(
            start_time=start_time,
            end_time=end_time,
        )

    def _merge_regions(
        self,
        regions: list[RegionOfInterest],
    ) -> list[RegionOfInterest]:
        if not regions:
            return []

        merged = [regions[0]]

        for current in regions[1:]:
            previous = merged[-1]
            gap = current.start_time - previous.end_time

            if gap <= ROI_MERGE_GAP:
                merged[-1] = RegionOfInterest(
                    start_time=previous.start_time,
                    end_time=max(
                        previous.end_time,
                        current.end_time,
                    ),
                )
            else:
                merged.append(current)

        return merged

    def _filter_and_pad_regions(
        self,
        regions: list[RegionOfInterest],
        audio_duration: float,
    ) -> list[RegionOfInterest]:
        processed: list[RegionOfInterest] = []

        for region in regions:
            if region.duration < ROI_MIN_DURATION:
                continue

            start_time = max(0.0, region.start_time - ROI_PADDING)
            end_time = min(
                audio_duration,
                region.end_time + ROI_PADDING,
            )

            processed.append(
                RegionOfInterest(
                    start_time=start_time,
                    end_time=end_time,
                )
            )

        return processed