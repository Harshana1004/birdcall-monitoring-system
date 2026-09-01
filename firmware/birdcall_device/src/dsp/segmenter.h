#pragma once

#include <cstddef>

#include "dsp/roi_detector.h"

namespace dsp {

// Extracts the exact ROI (no padding)

size_t extract_roi(
    const float* audio,
    size_t audio_length,
    uint32_t sample_rate,
    const RegionOfInterest& region,
    float* segment_out,
    size_t segment_out_capacity);

// Returns the number of samples extract_roi will produce for a
// given region, so callers can size segment_out correctly (or
// decide whether the ROI fits in remaining buffer/transmission
// budget) before calling extract_roi.
size_t extract_roi_sample_count(
    size_t audio_length,
    uint32_t sample_rate,
    const RegionOfInterest& region);

}  // namespace dsp