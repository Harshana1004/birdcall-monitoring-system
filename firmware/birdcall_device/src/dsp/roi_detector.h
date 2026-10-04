#pragma once

#include <cstddef>
#include <cstdint>

namespace dsp {

struct RegionOfInterest {
  float start_time_seconds;
  float end_time_seconds;
  // Loudest smoothed-energy frame inside the region (before
  // padding), in the same units as the energy curve.
  float peak_energy;

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
// A merged region's peak_energy is the max of its parts.
//
// Port of _merge_regions.
size_t merge_regions(
    RegionOfInterest* regions,
    size_t count,
    float merge_gap_seconds);


// Drops regions whose peak_energy is below min_peak_energy, in
// place; returns the new count. Edge-only step (not in the Python
// reference): the 2 x median threshold only marks a region's
// extent, and this decides whether it is loud enough to keep.
size_t gate_regions_by_peak(
    RegionOfInterest* regions,
    size_t count,
    float min_peak_energy);

size_t filter_and_pad_regions(
    RegionOfInterest* regions,
    size_t count,
    float min_duration_seconds,
    float padding_seconds,
    float audio_duration_seconds);

// raw regions -> merge -> peak gate -> min duration + padding.
// `rejected_out` (optional) receives the number of merged regions
// dropped by the peak gate.
size_t detect_regions(
    const float* smoothed_energy,
    size_t frame_count,
    float threshold,
    float min_peak_energy,
    uint32_t hop_length,
    uint32_t frame_length,
    uint32_t sample_rate,
    float merge_gap_seconds,
    float min_duration_seconds,
    float padding_seconds,
    float audio_duration_seconds,
    RegionOfInterest* regions_out,
    size_t regions_out_capacity,
    size_t* rejected_out = nullptr);

}  // namespace dsp