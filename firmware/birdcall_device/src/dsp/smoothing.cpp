#include "dsp/smoothing.h"

namespace dsp {

uint32_t clamp_window_size(uint32_t window_size, size_t energy_length) {
  if (energy_length == 0) {
    return window_size;  // caller should have already returned early
  }

  uint32_t clamped = window_size;

  if (clamped > energy_length) {
    clamped = static_cast<uint32_t>(energy_length);
  }

  if (clamped < 1) {
    clamped = 1;
  }

  return clamped;
}

size_t smooth_energy(
    const float* energy_in,
    size_t energy_length,
    uint32_t window_size,
    float* smoothed_out) {
  if (energy_length == 0) {
    return 0;
  }


  const int32_t K = static_cast<int32_t>(window_size);
  const int32_t offset = (K - 1) / 2;
  const int32_t N = static_cast<int32_t>(energy_length);

  for (int32_t i = 0; i < N; ++i) {
    double sum = 0.0;

    for (int32_t k = 0; k < K; ++k) {
      const int32_t idx = i + offset - k;

      if (idx >= 0 && idx < N) {
        sum += energy_in[idx];
      }
    }

    smoothed_out[i] = static_cast<float>(sum / K);
  }

  return energy_length;
}

}  // namespace dsp