#pragma once

#include <cstddef>

namespace dsp {

// Peak-normalizes audio in place to approximately [-1, 1].
// Returns the original peak absolute amplitude (0 if silent/empty).

float normalize_audio_in_place(float* audio, size_t length);

}  // namespace dsp