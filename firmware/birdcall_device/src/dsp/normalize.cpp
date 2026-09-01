#include "dsp/normalize.h"

#include <cmath>

namespace dsp {

void normalize_audio_in_place(float* audio, size_t length) {
  if (length == 0) {
    return;
  }

  float peak = 0.0f;

  for (size_t i = 0; i < length; ++i) {
    const float magnitude = std::fabs(audio[i]);
    if (magnitude > peak) {
      peak = magnitude;
    }
  }

  if (peak == 0.0f) {
    return;
  }

  for (size_t i = 0; i < length; ++i) {
    audio[i] /= peak;
  }
}

}  // namespace dsp