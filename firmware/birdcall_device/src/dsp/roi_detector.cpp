#include "dsp/roi_detector.h"

#include <algorithm>  // std::sort

namespace dsp {

float calculate_threshold(
    const float* smoothed_energy,
    size_t energy_length,
    float threshold_factor,
    float* scratch) {
  if (energy_length == 0) {
    return 0.0f;
  }

  for (size_t i = 0; i < energy_length; ++i) {
    scratch[i] = smoothed_energy[i];
  }

  std::sort(scratch, scratch + energy_length);

  float median;

  if (energy_length % 2 == 1) {
    median = scratch[energy_length / 2];
  } else {
    // np.median averages the two middle elements for even-length
    // arrays.
    const size_t upper = energy_length / 2;
    const size_t lower = upper - 1;
    median = (scratch[lower] + scratch[upper]) / 2.0f;
  }

  return median * threshold_factor;
}

size_t build_raw_regions(
    const float* smoothed_energy,
    size_t frame_count,
    float threshold,
    uint32_t hop_length,
    uint32_t frame_length,
    uint32_t sample_rate,
    RegionOfInterest* regions_out,
    size_t regions_out_capacity) {
  size_t written = 0;
  bool in_region = false;
  size_t start_frame = 0;

  auto frames_to_region = [&](size_t sf, size_t ef) -> RegionOfInterest {
    const float start_time =
        static_cast<float>(sf * hop_length) / sample_rate;

    const float end_time =
        static_cast<float>(ef * hop_length + frame_length) / sample_rate;

    return RegionOfInterest{start_time, end_time};
  };

  for (size_t i = 0; i < frame_count; ++i) {
    const bool is_active = smoothed_energy[i] >= threshold;

    if (is_active && !in_region) {
      start_frame = i;
      in_region = true;
    }

    if (!is_active && in_region) {
      if (written < regions_out_capacity) {
        regions_out[written] = frames_to_region(start_frame, i - 1);
        ++written;
      }
      in_region = false;
    }
  }

  if (in_region && written < regions_out_capacity) {
    regions_out[written] = frames_to_region(start_frame, frame_count - 1);
    ++written;
  }

  return written;
}

size_t merge_regions(
    RegionOfInterest* regions,
    size_t count,
    float merge_gap_seconds) {
  if (count == 0) {
    return 0;
  }

  size_t write_index = 0;  // index of the last kept ("previous") region

  for (size_t read_index = 1; read_index < count; ++read_index) {
    RegionOfInterest& previous = regions[write_index];
    const RegionOfInterest& current = regions[read_index];

    const float gap = current.start_time_seconds - previous.end_time_seconds;

    if (gap <= merge_gap_seconds) {
      previous.end_time_seconds =
          std::max(previous.end_time_seconds, current.end_time_seconds);
      // start_time_seconds stays as previous's, matching the Python
      // implementation, which keeps previous.start_time.
    } else {
      ++write_index;
      regions[write_index] = current;
    }
  }

  return write_index + 1;
}

size_t filter_and_pad_regions(
    RegionOfInterest* regions,
    size_t count,
    float min_duration_seconds,
    float padding_seconds,
    float audio_duration_seconds) {
  size_t write_index = 0;

  for (size_t read_index = 0; read_index < count; ++read_index) {
    const RegionOfInterest& region = regions[read_index];

    if (region.duration_seconds() < min_duration_seconds) {
      continue;
    }

    RegionOfInterest padded;

    padded.start_time_seconds =
        std::max(0.0f, region.start_time_seconds - padding_seconds);

    padded.end_time_seconds = std::min(
        audio_duration_seconds, region.end_time_seconds + padding_seconds);

    regions[write_index] = padded;
    ++write_index;
  }

  return write_index;
}

size_t detect_regions(
    const float* smoothed_energy,
    size_t frame_count,
    float threshold,
    uint32_t hop_length,
    uint32_t frame_length,
    uint32_t sample_rate,
    float merge_gap_seconds,
    float min_duration_seconds,
    float padding_seconds,
    float audio_duration_seconds,
    RegionOfInterest* regions_out,
    size_t regions_out_capacity) {
  if (frame_count == 0) {
    return 0;
  }

  const size_t raw_count = build_raw_regions(
      smoothed_energy, frame_count, threshold, hop_length, frame_length,
      sample_rate, regions_out, regions_out_capacity);

  const size_t merged_count =
      merge_regions(regions_out, raw_count, merge_gap_seconds);

  const size_t final_count = filter_and_pad_regions(
      regions_out, merged_count, min_duration_seconds, padding_seconds,
      audio_duration_seconds);

  return final_count;
}

}  // namespace dsp