#include "dsp/energy.h"

namespace dsp {

size_t short_time_energy_frame_count(
    size_t audio_length,
    uint32_t frame_length,
    uint32_t hop_length) {
  if (audio_length < frame_length) {
    return 0;
  }

  // Mirrors Python's range(0, audio_length - frame_length + 1, hop_length).
  const size_t limit = audio_length - frame_length + 1;

  return (limit + hop_length - 1) / hop_length;
}

size_t compute_short_time_energy(
    const float* audio,
    size_t audio_length,
    uint32_t frame_length,
    uint32_t hop_length,
    float* energy_out,
    size_t energy_out_capacity) {
  const size_t frame_count =
      short_time_energy_frame_count(audio_length, frame_length, hop_length);

  if (frame_count == 0 || energy_out_capacity < frame_count) {
    return 0;
  }

  size_t written = 0;

  for (size_t start = 0; written < frame_count;
       start += hop_length, ++written) {
    double sum_of_squares = 0.0;

    for (uint32_t i = 0; i < frame_length; ++i) {
      const float sample = audio[start + i];
      sum_of_squares += static_cast<double>(sample) * sample;
    }

    // mean(frame ** 2), matching np.mean semantics (double
    // accumulation avoids float32 rounding drift over 400 samples).
    energy_out[written] =
        static_cast<float>(sum_of_squares / frame_length);
  }

  return written;
}

}  // namespace dsp