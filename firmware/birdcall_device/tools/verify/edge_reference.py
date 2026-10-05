"""
Python reference for dsp::process_capture(): the backend's
AudioProcessingService steps, with the documented edge deviations
applied (see src/dsp/dsp_pipeline.h):

  * detection on a copy: causal 1 kHz sosfilt over the whole capture,
    then peak normalize
  * upload: the unfiltered capture, peak normalized
  * STE -> smoothing -> 2 x median threshold (backend code)
  * raw regions -> merge (backend rules, tracking each region's
    loudest smoothed frame) -> peak gate -> min duration + padding
    (backend code)
  * exact ROI extraction from the unfiltered capture, no 3 s padding

The gate constants are read from include/config.h so the reference
follows the firmware's settings.

Import from the other tools in this folder; needs the backend venv
(numpy, scipy) and backend/ on sys.path.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from scipy.signal import butter, sosfilt

from src.services.audio_processing import AudioProcessingService, RegionOfInterest

FIRMWARE = Path(__file__).resolve().parents[2]


def _config_float(name: str) -> float:
    text = (FIRMWARE / "include" / "config.h").read_text()
    match = re.search(rf"\b{name}\s*=\s*(-?[0-9.]+)f?\s*;", text)
    if match is None:
        raise RuntimeError(f"{name} not found in config.h")
    return float(match.group(1))


MIN_PEAK_FACTOR = _config_float("ROI_MIN_PEAK_FACTOR")
MIN_PEAK_DBFS = _config_float("ROI_MIN_PEAK_DBFS")
MIN_DURATION = _config_float("ROI_MIN_DURATION_SECONDS")
SAMPLE_RATE = int(_config_float("SAMPLE_RATE_HZ"))


@dataclass
class EdgeResult:
    frames: int = 0
    threshold: float = 0.0
    peak_threshold: float = float("inf")
    band_peak: float = 0.0
    input_peak: float = 0.0
    noise_floor_dbfs: float = -150.0
    loudest_dbfs: float = -150.0
    rejected: int = 0
    # (region index, start s, end s, unfiltered normalized samples)
    rois: list[tuple[int, float, float, np.ndarray]] = field(default_factory=list)


def _to_dbfs(energy: float, band_peak: float) -> float:
    absolute = energy * band_peak * band_peak
    return 10.0 * np.log10(absolute) if absolute > 0 else -150.0


def edge_pipeline(audio: np.ndarray, sr: int = SAMPLE_RATE) -> EdgeResult:
    service = AudioProcessingService(sample_rate=sr, roi_min_duration=MIN_DURATION)
    result = EdgeResult()

    sos = butter(4, 1000.0 / (sr / 2), btype="highpass", output="sos")
    filtered = sosfilt(sos, np.asarray(audio, dtype=np.float32)).astype(np.float32)
    result.band_peak = float(np.max(np.abs(filtered))) if filtered.size else 0.0
    normalized = service.normalize_audio(filtered)

    raw = np.asarray(audio, dtype=np.float32)
    result.input_peak = float(np.max(np.abs(raw))) if raw.size else 0.0
    upload = service.normalize_audio(raw)

    energy = service.compute_short_time_energy(normalized)
    smoothed = service.smooth_energy(energy)
    result.frames = len(smoothed)
    if smoothed.size == 0:
        return result

    threshold = service.calculate_threshold(smoothed)
    result.threshold = float(threshold)
    median = threshold / service.roi_threshold_factor
    result.noise_floor_dbfs = _to_dbfs(median, result.band_peak)
    result.loudest_dbfs = _to_dbfs(float(smoothed.max()), result.band_peak)

    if result.band_peak > 0:
        floor = 10.0 ** (MIN_PEAK_DBFS / 10.0) / result.band_peak**2
        result.peak_threshold = max(threshold, MIN_PEAK_FACTOR * median, floor)

    # Raw regions with their loudest frame.
    raw: list[tuple[RegionOfInterest, float]] = []
    start = None
    for i, active in enumerate(smoothed >= threshold):
        if active and start is None:
            start = i
        if not active and start is not None:
            raw.append((service._frames_to_region(start, i - 1),
                        float(smoothed[start:i].max())))
            start = None
    if start is not None:
        raw.append((service._frames_to_region(start, len(smoothed) - 1),
                    float(smoothed[start:].max())))

    # Backend merge rule, keeping the max peak.
    merged: list[tuple[RegionOfInterest, float]] = []
    for region, peak in raw:
        if merged and region.start_time - merged[-1][0].end_time <= service.roi_merge_gap:
            prev, prev_peak = merged[-1]
            merged[-1] = (
                RegionOfInterest(start_time=prev.start_time,
                                 end_time=max(prev.end_time, region.end_time)),
                max(prev_peak, peak),
            )
        else:
            merged.append((region, peak))

    loud = [region for region, peak in merged if peak >= result.peak_threshold]
    result.rejected = len(merged) - len(loud)

    regions = service._filter_and_pad_regions(loud, audio_duration=len(normalized) / sr)

    for index, region in enumerate(regions):
        s = max(0, int(round(region.start_time * sr)))
        e = min(len(upload), int(round(region.end_time * sr)))
        if e <= s:
            continue
        result.rois.append((index, region.start_time, region.end_time,
                            np.asarray(upload[s:e], dtype=np.float32)))
    return result
