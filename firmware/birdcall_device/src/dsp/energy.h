#pragma once

#include <cstddef>
#include <cstdint>

namespace dsp {

// Computes mean-squared energy over overlapping frames.

size_t compute_short_time_energy(
    const float* audio,
    size_t audio_length,
    uint32_t frame_length,
    uint32_t hop_length,
    float* energy_out,
    size_t energy_out_capacity);

// Returns the exact number of frames compute_short_time_energy
// will produce for a given audio_length, so callers can size
// energy_out correctly before calling. Mirrors the same range()
// stepping logic as the Python implementation.
size_t short_time_energy_frame_count(
    size_t audio_length,
    uint32_t frame_length,
    uint32_t hop_length);

}  // namespace dsp