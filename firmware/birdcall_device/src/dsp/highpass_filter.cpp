#include "dsp/highpass_filter.h"

#include "highpass_coeffs.h"

namespace dsp {

void apply_highpass_filter(float* audio, size_t length) {
  if (length == 0) {
    return;
  }

  // Direct Form II Transposed, one section at a time, output of
  // each section feeding the next -- this is exactly what
  // scipy.signal.sosfilt does for a single forward pass (the
  // causal half of what sosfiltfilt does twice). Per-section
  // state (z1, z2) starts at zero, matching sosfilt's default
  // zero initial conditions.
  for (int section = 0; section < HIGHPASS_SECTION_COUNT; ++section) {
    const float b0 = HIGHPASS_SOS[section][0];
    const float b1 = HIGHPASS_SOS[section][1];
    const float b2 = HIGHPASS_SOS[section][2];
    // HIGHPASS_SOS[section][3] is a0, always 1.0 for this filter
    // design (see highpass_coeffs.h) -- omitted from the
    // recurrence below since dividing by 1.0 is a no-op.
    const float a1 = HIGHPASS_SOS[section][4];
    const float a2 = HIGHPASS_SOS[section][5];

    float z1 = 0.0f;
    float z2 = 0.0f;

    for (size_t i = 0; i < length; ++i) {
      const float x = audio[i];
      const float y = b0 * x + z1;

      z1 = b1 * x - a1 * y + z2;
      z2 = b2 * x - a2 * y;

      audio[i] = y;
    }
  }
}

}  // namespace dsp