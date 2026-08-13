from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf
from scipy.signal import (
    butter,
    sosfiltfilt,
)


# ============================================================
# Processing configuration
# ============================================================


TARGET_SAMPLE_RATE = 16000
MONO = True

FRAME_DURATION = 0.025
HOP_DURATION = 0.010

ROI_THRESHOLD_FACTOR = 2.0
ROI_MIN_DURATION = 0.30
ROI_MERGE_GAP = 0.50
ROI_PADDING = 0.25

HIGHPASS_CUTOFF = 1000.0
HIGHPASS_FILTER_ORDER = 4

BIRDNET_MIN_DURATION = 3.0


# ============================================================
# Data models
# ============================================================


@dataclass(
    frozen=True
)
class RegionOfInterest:
    """
    One acoustic Region of Interest detected in the original
    uploaded recording.
    """

    start_time: float
    end_time: float

    @property
    def duration(
        self,
    ) -> float:
        return (
            self.end_time
            - self.start_time
        )


@dataclass(
    frozen=True
)
class ProcessedROI:
    """
    One extracted and filtered ROI ready for BirdNET.

    region describes the position of the ROI in the original
    recording.

    audio contains the final BirdNET-ready audio. If the
    detected ROI was shorter than BirdNET's minimum duration,
    it is centre-padded with silence.
    """

    index: int
    region: RegionOfInterest
    audio: np.ndarray

    @property
    def original_duration_seconds(
        self,
    ) -> float:
        return (
            self.region.duration
        )


@dataclass(
    frozen=True
)
class AudioProcessingResult:
    """
    Complete output of the manual-upload audio processing
    pipeline.
    """

    original_filename: str

    sample_rate: int
    duration_seconds: float

    normalized_audio: np.ndarray

    energy: np.ndarray
    energy_times: np.ndarray
    energy_threshold: float

    rois: list[
        ProcessedROI
    ]


# ============================================================
# Audio processing service
# ============================================================


class AudioProcessingService:
    """
    Process a complete manually uploaded audio recording.

    Pipeline:

        load/resample/mono
            ↓
        peak normalization
            ↓
        short-time energy
            ↓
        energy smoothing
            ↓
        adaptive ROI detection
            ↓
        merge/filter/pad ROI boundaries
            ↓
        exact ROI extraction
            ↓
        silence pad short snippets to 3 seconds
            ↓
        1 kHz Butterworth high-pass filter
            ↓
        BirdNET-ready ROI snippets

    This service contains no database or FastAPI logic.
    """

    def __init__(
        self,
        *,
        sample_rate: int = TARGET_SAMPLE_RATE,
        frame_duration: float = FRAME_DURATION,
        hop_duration: float = HOP_DURATION,
        roi_threshold_factor: float = ROI_THRESHOLD_FACTOR,
        roi_min_duration: float = ROI_MIN_DURATION,
        roi_merge_gap: float = ROI_MERGE_GAP,
        roi_padding: float = ROI_PADDING,
        highpass_cutoff: float = HIGHPASS_CUTOFF,
        highpass_filter_order: int = HIGHPASS_FILTER_ORDER,
        birdnet_min_duration: float = BIRDNET_MIN_DURATION,
    ) -> None:
        if sample_rate <= 0:
            raise ValueError(
                "sample_rate must be greater than zero."
            )

        if frame_duration <= 0:
            raise ValueError(
                "frame_duration must be greater than zero."
            )

        if hop_duration <= 0:
            raise ValueError(
                "hop_duration must be greater than zero."
            )

        if roi_threshold_factor <= 0:
            raise ValueError(
                "roi_threshold_factor must be greater than zero."
            )

        if roi_min_duration < 0:
            raise ValueError(
                "roi_min_duration cannot be negative."
            )

        if roi_merge_gap < 0:
            raise ValueError(
                "roi_merge_gap cannot be negative."
            )

        if roi_padding < 0:
            raise ValueError(
                "roi_padding cannot be negative."
            )

        if highpass_cutoff <= 0:
            raise ValueError(
                "highpass_cutoff must be greater than zero."
            )

        if highpass_filter_order <= 0:
            raise ValueError(
                "highpass_filter_order must be greater than zero."
            )

        if birdnet_min_duration <= 0:
            raise ValueError(
                "birdnet_min_duration must be greater than zero."
            )

        self.sample_rate = (
            sample_rate
        )

        self.frame_duration = (
            frame_duration
        )

        self.hop_duration = (
            hop_duration
        )

        self.roi_threshold_factor = (
            roi_threshold_factor
        )

        self.roi_min_duration = (
            roi_min_duration
        )

        self.roi_merge_gap = (
            roi_merge_gap
        )

        self.roi_padding = (
            roi_padding
        )

        self.highpass_cutoff = (
            highpass_cutoff
        )

        self.highpass_filter_order = (
            highpass_filter_order
        )

        self.birdnet_min_duration = (
            birdnet_min_duration
        )

        self.frame_length = int(
            self.frame_duration
            * self.sample_rate
        )

        self.hop_length = int(
            self.hop_duration
            * self.sample_rate
        )

    # ========================================================
    # Main processing pipeline
    # ========================================================

    def process(
        self,
        file_path: str | Path,
    ) -> AudioProcessingResult:
        """
        Process one complete raw audio recording.
        """

        path = Path(
            file_path
        )

        audio, sample_rate = (
            self.load_audio(
                path
            )
        )

        normalized_audio = (
            self.normalize_audio(
                audio
            )
        )

        (
            regions,
            smoothed_energy,
            threshold,
        ) = self.detect_regions(
            normalized_audio
        )

        processed_rois: list[
            ProcessedROI
        ] = []

        for index, region in enumerate(
            regions
        ):
            segment = (
                self.extract_roi(
                    normalized_audio,
                    sample_rate,
                    region,
                )
            )

            if segment.size == 0:
                continue

            filtered_segment = (
                self.apply_highpass_filter(
                    segment,
                    sample_rate,
                )
            )

            processed_rois.append(
                ProcessedROI(
                    index=index,
                    region=region,
                    audio=filtered_segment,
                )
            )

        energy_times = (
            np.arange(
                len(
                    smoothed_energy
                ),
                dtype=np.float32,
            )
            * self.hop_duration
        )

        duration_seconds = (
            len(
                normalized_audio
            )
            / sample_rate
        )

        return AudioProcessingResult(
            original_filename=(
                path.name
            ),

            sample_rate=(
                sample_rate
            ),

            duration_seconds=float(
                duration_seconds
            ),

            normalized_audio=(
                normalized_audio
            ),

            energy=(
                smoothed_energy
            ),

            energy_times=(
                energy_times
            ),

            energy_threshold=float(
                threshold
            ),

            rois=(
                processed_rois
            ),
        )

    # ========================================================
    # Audio loading
    # ========================================================

    def load_audio(
        self,
        file_path: str | Path,
    ) -> tuple[
        np.ndarray,
        int,
    ]:
        """
        Load an audio file, convert it to mono and resample it
        to the configured target sample rate.
        """

        path = Path(
            file_path
        )

        if not path.exists():
            raise FileNotFoundError(
                f"Audio file not found: {path}"
            )

        if not path.is_file():
            raise ValueError(
                f"Audio path is not a file: {path}"
            )

        audio, sample_rate = (
            librosa.load(
                path,
                sr=self.sample_rate,
                mono=MONO,
            )
        )

        return (
            np.asarray(
                audio,
                dtype=np.float32,
            ),
            int(
                sample_rate
            ),
        )

    # ========================================================
    # Normalization
    # ========================================================

    @staticmethod
    def normalize_audio(
        audio: np.ndarray,
    ) -> np.ndarray:
        """
        Peak-normalize audio amplitude to [-1, 1].
        """

        if audio.size == 0:
            return (
                audio.copy()
            )

        peak = float(
            np.max(
                np.abs(
                    audio
                )
            )
        )

        if peak == 0:
            return (
                audio.copy()
            )

        normalized = (
            audio
            / peak
        )

        return np.asarray(
            normalized,
            dtype=np.float32,
        )

    # ========================================================
    # Short-time energy
    # ========================================================

    def compute_short_time_energy(
        self,
        audio: np.ndarray,
    ) -> np.ndarray:
        """
        Calculate mean-squared energy over overlapping frames.
        """

        if (
            audio.size
            < self.frame_length
        ):
            return np.array(
                [],
                dtype=np.float32,
            )

        energy_values: list[
            float
        ] = []

        for start in range(
            0,
            (
                len(audio)
                - self.frame_length
                + 1
            ),
            self.hop_length,
        ):
            frame = audio[
                start:
                start
                + self.frame_length
            ]

            frame_energy = float(
                np.mean(
                    frame ** 2
                )
            )

            energy_values.append(
                frame_energy
            )

        return np.asarray(
            energy_values,
            dtype=np.float32,
        )

    # ========================================================
    # Energy smoothing
    # ========================================================

    @staticmethod
    def smooth_energy(
        energy: np.ndarray,
        window_size: int = 15,
    ) -> np.ndarray:
        """
        Smooth the energy curve using the same moving-average
        method as the evaluated pipeline.
        """

        if energy.size == 0:
            return (
                energy.copy()
            )

        window_size = max(
            1,
            min(
                window_size,
                len(
                    energy
                ),
            ),
        )

        kernel = (
            np.ones(
                window_size,
                dtype=np.float32,
            )
            / window_size
        )

        smoothed = np.convolve(
            energy,
            kernel,
            mode="same",
        )

        return np.asarray(
            smoothed,
            dtype=np.float32,
        )

    # ========================================================
    # Adaptive energy threshold
    # ========================================================

    def calculate_threshold(
        self,
        smoothed_energy: np.ndarray,
    ) -> float:
        """
        Calculate the adaptive ROI threshold.

        threshold =
            median(smoothed_energy)
            × ROI_THRESHOLD_FACTOR
        """

        if (
            smoothed_energy.size
            == 0
        ):
            return 0.0

        median_energy = float(
            np.median(
                smoothed_energy
            )
        )

        return (
            median_energy
            * self.roi_threshold_factor
        )

    # ========================================================
    # ROI detection
    # ========================================================

    def detect_regions(
        self,
        audio: np.ndarray,
    ) -> tuple[
        list[
            RegionOfInterest
        ],
        np.ndarray,
        float,
    ]:
        """
        Detect active acoustic regions using short-time energy.
        """

        energy = (
            self.compute_short_time_energy(
                audio
            )
        )

        smoothed_energy = (
            self.smooth_energy(
                energy
            )
        )

        threshold = (
            self.calculate_threshold(
                smoothed_energy
            )
        )

        if (
            smoothed_energy.size
            == 0
        ):
            return (
                [],
                smoothed_energy,
                threshold,
            )

        active_frames = (
            smoothed_energy
            >= threshold
        )

        raw_regions = (
            self._active_frames_to_regions(
                active_frames
            )
        )

        merged_regions = (
            self._merge_regions(
                raw_regions
            )
        )

        filtered_regions = (
            self._filter_and_pad_regions(
                merged_regions,
                audio_duration=(
                    len(audio)
                    / self.sample_rate
                ),
            )
        )

        return (
            filtered_regions,
            smoothed_energy,
            threshold,
        )

    # ========================================================
    # Active-frame conversion
    # ========================================================

    def _active_frames_to_regions(
        self,
        active_frames: np.ndarray,
    ) -> list[
        RegionOfInterest
    ]:
        regions: list[
            RegionOfInterest
        ] = []

        start_frame: (
            int | None
        ) = None

        for (
            index,
            is_active,
        ) in enumerate(
            active_frames
        ):
            if (
                is_active
                and start_frame is None
            ):
                start_frame = (
                    index
                )

            if (
                not is_active
                and start_frame is not None
            ):
                regions.append(
                    self._frames_to_region(
                        start_frame,
                        index - 1,
                    )
                )

                start_frame = None

        if start_frame is not None:
            regions.append(
                self._frames_to_region(
                    start_frame,
                    len(
                        active_frames
                    ) - 1,
                )
            )

        return regions

    def _frames_to_region(
        self,
        start_frame: int,
        end_frame: int,
    ) -> RegionOfInterest:
        start_time = (
            start_frame
            * self.hop_length
            / self.sample_rate
        )

        end_time = (
            (
                end_frame
                * self.hop_length
            )
            + self.frame_length
        ) / self.sample_rate

        return RegionOfInterest(
            start_time=float(
                start_time
            ),
            end_time=float(
                end_time
            ),
        )

    # ========================================================
    # ROI merging
    # ========================================================

    def _merge_regions(
        self,
        regions: list[
            RegionOfInterest
        ],
    ) -> list[
        RegionOfInterest
    ]:
        """
        Merge neighboring acoustic regions separated by no more
        than ROI_MERGE_GAP.
        """

        if not regions:
            return []

        merged = [
            regions[0]
        ]

        for current in regions[
            1:
        ]:
            previous = (
                merged[-1]
            )

            gap = (
                current.start_time
                - previous.end_time
            )

            if (
                gap
                <= self.roi_merge_gap
            ):
                merged[-1] = (
                    RegionOfInterest(
                        start_time=(
                            previous.start_time
                        ),
                        end_time=max(
                            previous.end_time,
                            current.end_time,
                        ),
                    )
                )

            else:
                merged.append(
                    current
                )

        return merged

    # ========================================================
    # ROI duration filtering / boundary padding
    # ========================================================

    def _filter_and_pad_regions(
        self,
        regions: list[
            RegionOfInterest
        ],
        *,
        audio_duration: float,
    ) -> list[
        RegionOfInterest
    ]:
        """
        Remove very short regions and add the configured boundary
        margin.

        Note that this is different from the later BirdNET
        silence padding operation.
        """

        processed: list[
            RegionOfInterest
        ] = []

        for region in regions:
            if (
                region.duration
                < self.roi_min_duration
            ):
                continue

            start_time = max(
                0.0,
                (
                    region.start_time
                    - self.roi_padding
                ),
            )

            end_time = min(
                audio_duration,
                (
                    region.end_time
                    + self.roi_padding
                ),
            )

            processed.append(
                RegionOfInterest(
                    start_time=float(
                        start_time
                    ),
                    end_time=float(
                        end_time
                    ),
                )
            )

        return processed

    # ========================================================
    # ROI extraction
    # ========================================================

    def extract_roi(
        self,
        audio: np.ndarray,
        sample_rate: int,
        region: RegionOfInterest,
    ) -> np.ndarray:
        """
        Extract exactly the detected ROI.

        If it is shorter than BirdNET's minimum 3-second input,
        centre-pad it with silence.

        Longer ROIs are preserved unchanged.
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
            round(
                region.start_time
                * sample_rate
            )
        )

        end_sample = int(
            round(
                region.end_time
                * sample_rate
            )
        )

        start_sample = max(
            0,
            start_sample,
        )

        end_sample = min(
            len(
                audio
            ),
            end_sample,
        )

        if (
            end_sample
            <= start_sample
        ):
            return np.array(
                [],
                dtype=audio.dtype,
            )

        segment = (
            audio[
                start_sample:
                end_sample
            ]
            .copy()
        )

        return (
            self._pad_to_birdnet_duration(
                segment,
                sample_rate,
            )
        )

    def _pad_to_birdnet_duration(
        self,
        segment: np.ndarray,
        sample_rate: int,
    ) -> np.ndarray:
        """
        Centre-pad short segments with silence.

        Segments at least 3 seconds long are not cropped.
        """

        minimum_samples = int(
            round(
                self.birdnet_min_duration
                * sample_rate
            )
        )

        current_samples = len(
            segment
        )

        if (
            current_samples
            >= minimum_samples
        ):
            return (
                segment.copy()
            )

        missing_samples = (
            minimum_samples
            - current_samples
        )

        padding_before = (
            missing_samples
            // 2
        )

        padding_after = (
            missing_samples
            - padding_before
        )

        padded_segment = (
            np.pad(
                segment,
                pad_width=(
                    padding_before,
                    padding_after,
                ),
                mode="constant",
                constant_values=0,
            )
        )

        return (
            padded_segment.astype(
                segment.dtype,
                copy=False,
            )
        )

    # ========================================================
    # High-pass filtering
    # ========================================================

    def apply_highpass_filter(
        self,
        audio: np.ndarray,
        sample_rate: int,
    ) -> np.ndarray:
        """
        Apply the evaluated fourth-order Butterworth high-pass
        filter using zero-phase filtering.
        """

        if audio.size == 0:
            return (
                audio.copy()
            )

        nyquist_frequency = (
            sample_rate
            / 2.0
        )

        if (
            self.highpass_cutoff
            >= nyquist_frequency
        ):
            raise ValueError(
                "High-pass cutoff frequency must be below "
                "the Nyquist frequency."
            )

        normalized_cutoff = (
            self.highpass_cutoff
            / nyquist_frequency
        )

        second_order_sections = (
            butter(
                N=(
                    self.highpass_filter_order
                ),
                Wn=(
                    normalized_cutoff
                ),
                btype="highpass",
                output="sos",
            )
        )

        minimum_samples = (
            3
            * (
                2
                * len(
                    second_order_sections
                )
                + 1
            )
        )

        if (
            len(
                audio
            )
            <= minimum_samples
        ):
            return (
                audio.copy()
            )

        filtered_audio = (
            sosfiltfilt(
                second_order_sections,
                audio,
            )
        )

        return (
            filtered_audio.astype(
                np.float32
            )
        )

    # ========================================================
    # ROI persistence
    # ========================================================

    @staticmethod
    def save_roi(
        audio: np.ndarray,
        sample_rate: int,
        output_path: str | Path,
    ) -> Path:
        """
        Save one processed ROI as mono 16-bit PCM WAV.
        """

        if audio.size == 0:
            raise ValueError(
                "Cannot save an empty audio ROI."
            )

        path = Path(
            output_path
        )

        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        sf.write(
            path,
            audio,
            sample_rate,
            subtype="PCM_16",
        )

        return path