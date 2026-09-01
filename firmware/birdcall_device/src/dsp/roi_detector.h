#pragma once

#include <cstddef>
#include <cstdint>

namespace dsp {

struct RegionOfInterest {
  float start_time_seconds;
  float end_time_seconds;

  float duration_seconds() const {
    return end_time_seconds - start_time_seconds;
  }
};


float calculate_threshold(
    const float* smoothed_energy,
    size_t energy_length,
    float threshold_factor,
    float* scratch);



size_t build_raw_regions(
    const float* smoothed_energy,
    size_t frame_count,
    float threshold,
    uint32_t hop_length,
    uint32_t frame_length,
    uint32_t sample_rate,
    RegionOfInterest* regions_out,
    size_t regions_out_capacity);

// Merges neighboring regions separated by <= merge_gap_seconds.
// Operates in place; returns the new (possibly smaller) count.
//
// Direct port of _merge_regions.
size_t merge_regions(
    RegionOfInterest* regions,
    size_t count,
    float merge_gap_seconds);


size_t filter_and_pad_regions(
    RegionOfInterest* regions,
    size_t count,
    float min_duration_seconds,
    float padding_seconds,
    float audio_duration_seconds);

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
    size_t regions_out_capacity);

}  // namespace dsp