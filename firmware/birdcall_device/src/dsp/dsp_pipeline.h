#pragma once

#include <cstddef>
#include <cstdint>

#include "dsp/roi_detector.h"

namespace dsp {

// Caller-owned buffers for one process_capture() call. The
// pipeline never allocates; the capture layer decides what lives
// in PSRAM vs internal RAM.
struct PipelineWorkspace {
  // Both must hold at least
  // short_time_energy_frame_count(audio_length, ...) floats.
  // energy_scratch is reused as the median-sort scratch once the
  // energy curve has been smoothed.
  float* energy_scratch;
  float* smoothed_energy;
  size_t frame_capacity;

  RegionOfInterest* regions;
  size_t region_capacity;

  // Must hold at least audio_length floats. Used first as the
  // scratch copy for the high-passed detection signal, then the ROI
  // audio is written back-to-back into it.
  float* roi_arena;
  size_t roi_arena_capacity;
};

// One extracted ROI (unfiltered, peak-normalised), ready for upload.
// `audio` points into PipelineWorkspace::roi_arena.
struct ProcessedRoi {
  // Position in the detected region list (matches Python's
  // enumerate() index, so skipped empty ROIs leave gaps).
  uint32_t index;
  RegionOfInterest region;
  const float* audio;
  size_t sample_count;
};

enum class PipelineStatus {
  kOk,
  // Audio shorter than one STE frame -- nothing to detect.
  kAudioTooShort,
  // Energy buffers smaller than the frame count.
  kFrameCapacityTooSmall,
  // roi_arena smaller than the audio (it holds the detection copy).
  kArenaTooSmall,
  // Some ROIs were dropped because processed_out or the arena
  // filled up. Returned ROIs are still valid. (detect_regions caps
  // silently at region_capacity, so size `regions` generously.)
  kTruncated,
};

struct PipelineResult {
  PipelineStatus status;
  size_t frame_count;
  // 2 x median: marks where a region starts and ends.
  float energy_threshold;
  // A region is kept only if its loudest frame reaches this:
  // max(ROI_MIN_PEAK_FACTOR x median, the ROI_MIN_PEAK_DBFS floor).
  float peak_threshold;
  float duration_seconds;
  // Peak absolute amplitude of the capture (the divisor of the
  // uploaded, unfiltered audio).
  float input_peak;
  // Peak absolute amplitude of the high-passed detection copy (its
  // normalisation divisor).
  float band_peak;
  // Absolute in-band levels of this capture, dBFS (mean-square
  // energy of the smoothed curve, full scale = 1.0): the median is
  // the noise floor, the max the loudest moment.
  float noise_floor_dbfs;
  float loudest_dbfs;
  size_t detected_region_count;
  // Merged regions dropped by the peak gate.
  size_t rejected_region_count;
  size_t roi_count;
};

// Returns the number of energy frames process_capture() will need
// for `audio_length` samples, for sizing the workspace.
size_t pipeline_frame_count(size_t audio_length);

// Runs the full on-device pipeline over one capture buffer:
//
//   detection copy (in roi_arena): causal 1 kHz high-pass
//     -> peak normalize
//     -> short-time energy -> smoothing -> 2 x median threshold
//     -> active frames -> merge -> peak gate -> filter / pad regions
//   upload: peak normalize the capture (in place, unfiltered)
//     -> exact ROI extraction
//
// Based on AudioProcessingService.process(), with documented edge
// deviations:
//   - ROIs are not padded to 3 s (the backend does that);
//   - the high-pass is single-pass causal, not zero-phase
//     sosfiltfilt, and is used for detection only: energy is
//     measured in the band birds use (hum, wind and knocks do not
//     trigger ROIs), but the uploaded ROI is unfiltered. BirdNET was
//     trained on unfiltered audio; on the Western Amazon evaluation
//     the 1 kHz-filtered upload let BirdNET find ~half as many calls
//     inside ROIs (evaluation_ea/results/padding_aggregation);
//   - the peak gate: a region must reach ROI_MIN_PEAK_FACTOR x the
//     median and the absolute ROI_MIN_PEAK_DBFS floor, so windows
//     holding only noise produce no ROIs.
//
// `audio` is modified in place (peak-normalized, not filtered).
PipelineResult process_capture(
    float* audio,
    size_t audio_length,
    const PipelineWorkspace& workspace,
    ProcessedRoi* processed_out,
    size_t processed_out_capacity);

}  // namespace dsp
