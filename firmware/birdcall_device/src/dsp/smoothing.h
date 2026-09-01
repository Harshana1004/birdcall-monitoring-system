#pragma once

#include <cstddef>
#include <cstdint>

namespace dsp {

// Smooths an energy curve using a moving average.

size_t smooth_energy(
    const float* energy_in,
    size_t energy_length,
    uint32_t window_size,
    float* smoothed_out);

// Mirrors: window_size = max(1, min(window_size, len(energy)))
uint32_t clamp_window_size(uint32_t window_size, size_t energy_length);

}  // namespace dsp