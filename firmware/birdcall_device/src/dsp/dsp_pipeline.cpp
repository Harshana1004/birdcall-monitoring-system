#include "dsp/dsp_pipeline.h"

#include "config.h"
#include "dsp/energy.h"
#include "dsp/highpass_filter.h"
#include "dsp/normalize.h"
#include "dsp/segmenter.h"
#include "dsp/smoothing.h"

namespace dsp {

size_t pipeline_frame_count(size_t audio_length) {
  return short_time_energy_frame_count(audio_length, FRAME_LENGTH_SAMPLES,
                                       HOP_LENGTH_SAMPLES);
}

PipelineResult process_capture(
    float* audio,
    size_t audio_length,
    const PipelineWorkspace& workspace,
    ProcessedRoi* processed_out,
    size_t processed_out_capacity) {
  PipelineResult result{};
  result.status = PipelineStatus::kOk;
  result.duration_seconds =
      static_cast<float>(audio_length) / SAMPLE_RATE_HZ;

  result.input_peak = normalize_audio_in_place(audio, audio_length);

  const size_t frame_count = pipeline_frame_count(audio_length);
  result.frame_count = frame_count;

  if (frame_count == 0) {
    result.status = PipelineStatus::kAudioTooShort;
    return result;
  }

  if (workspace.frame_capacity < frame_count) {
    result.status = PipelineStatus::kFrameCapacityTooSmall;
    return result;
  }

  compute_short_time_energy(audio, audio_length, FRAME_LENGTH_SAMPLES,
                            HOP_LENGTH_SAMPLES, workspace.energy_scratch,
                            workspace.frame_capacity);

  const uint32_t window =
      clamp_window_size(ENERGY_SMOOTHING_WINDOW, frame_count);

  smooth_energy(workspace.energy_scratch, frame_count, window,
                workspace.smoothed_energy);

  // Raw energy is no longer needed; reuse it as the sort scratch.
  const float threshold =
      calculate_threshold(workspace.smoothed_energy, frame_count,
                          ROI_THRESHOLD_FACTOR, workspace.energy_scratch);
  result.energy_threshold = threshold;

  const size_t region_count = detect_regions(
      workspace.smoothed_energy, frame_count, threshold, HOP_LENGTH_SAMPLES,
      FRAME_LENGTH_SAMPLES, SAMPLE_RATE_HZ, ROI_MERGE_GAP_SECONDS,
      ROI_MIN_DURATION_SECONDS, ROI_PADDING_SECONDS,
      result.duration_seconds, workspace.regions,
      workspace.region_capacity);
  result.detected_region_count = region_count;

  size_t arena_used = 0;

  for (size_t i = 0; i < region_count; ++i) {
    const RegionOfInterest& region = workspace.regions[i];

    const size_t needed =
        extract_roi_sample_count(audio_length, SAMPLE_RATE_HZ, region);

    // Matches Python: `if segment.size == 0: continue`.
    if (needed == 0) {
      continue;
    }

    if (result.roi_count >= processed_out_capacity ||
        needed > workspace.roi_arena_capacity - arena_used) {
      result.status = PipelineStatus::kTruncated;
      break;
    }

    float* segment = workspace.roi_arena + arena_used;

    const size_t extracted = extract_roi(audio, audio_length, SAMPLE_RATE_HZ,
                                         region, segment, needed);

    apply_highpass_filter(segment, extracted);

    processed_out[result.roi_count] =
        ProcessedRoi{static_cast<uint32_t>(i), region, segment, extracted};

    ++result.roi_count;
    arena_used += extracted;
  }

  return result;
}

}  // namespace dsp
