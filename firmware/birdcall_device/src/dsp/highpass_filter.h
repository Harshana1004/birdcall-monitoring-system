#pragma once

#include <cstddef>

namespace dsp {

// Applies the 4th-order 1000 Hz Butterworth high-pass filter to
// `audio` in place, using a causal (single forward pass) Direct
// Form II Transposed biquad cascade over the precomputed SOS
// coefficients in highpass_coeffs.h.

void apply_highpass_filter(float* audio, size_t length);

}  // namespace dsp