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

  // Filtered ROI audio is written back-to-back into this arena.
  float* roi_arena;
  size_t roi_arena_capacity;
};

// One extracted + high-pass filtered ROI, ready for upload.
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
  // Some ROIs were dropped because processed_out or the arena
  // filled up. Returned ROIs are still valid. (detect_regions caps
  // silently at region_capacity, so size `regions` generously.)
  kTruncated,
};

struct PipelineResult {
  PipelineStatus status;
  size_t frame_count;
  float energy_threshold;
  float duration_seconds;
  size_t detected_region_count;
  size_t roi_count;
};

// Returns the number of energy frames process_capture() will need
// for `audio_length` samples, for sizing the workspace.
size_t pipeline_frame_count(size_t audio_length);

// Runs the full on-device pipeline over one capture buffer:
//
//   peak normalize (in place)
//     -> short-time energy -> smoothing -> 2 x median threshold
//     -> active frames -> merge / filter / pad regions
//     -> exact ROI extraction -> causal 1 kHz high-pass filter
//
// Mirrors AudioProcessingService.process() with two documented
// deviations: ROIs are not padded to 3 s (the backend does that),
// and the high-pass filter is single-pass causal rather than
// zero-phase sosfiltfilt.
//
// `audio` is modified in place (normalized).
PipelineResult process_capture(
    float* audio,
    size_t audio_length,
    const PipelineWorkspace& workspace,
    ProcessedRoi* processed_out,
    size_t processed_out_capacity);

}  // namespace dsp
