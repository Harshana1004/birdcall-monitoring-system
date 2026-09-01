#include "dsp/segmenter.h"

#include <algorithm>
#include <cmath>

namespace dsp {

namespace {

size_t seconds_to_sample_index(float seconds, uint32_t sample_rate,
                                size_t audio_length) {
  long rounded = std::lround(static_cast<double>(seconds) * sample_rate);

  if (rounded < 0) {
    rounded = 0;
  }

  if (static_cast<size_t>(rounded) > audio_length) {
    rounded = static_cast<long>(audio_length);
  }

  return static_cast<size_t>(rounded);
}

}  // namespace

size_t extract_roi_sample_count(
    size_t audio_length,
    uint32_t sample_rate,
    const RegionOfInterest& region) {
  const size_t start_sample = seconds_to_sample_index(
      region.start_time_seconds, sample_rate, audio_length);

  const size_t end_sample = seconds_to_sample_index(
      region.end_time_seconds, sample_rate, audio_length);

  if (end_sample <= start_sample) {
    return 0;
  }

  return end_sample - start_sample;
}

size_t extract_roi(
    const float* audio,
    size_t audio_length,
    uint32_t sample_rate,
    const RegionOfInterest& region,
    float* segment_out,
    size_t segment_out_capacity) {
  if (audio_length == 0) {
    return 0;
  }

  const size_t start_sample = seconds_to_sample_index(
      region.start_time_seconds, sample_rate, audio_length);

  const size_t end_sample = seconds_to_sample_index(
      region.end_time_seconds, sample_rate, audio_length);

  if (end_sample <= start_sample) {
    return 0;
  }

  const size_t count = end_sample - start_sample;
  const size_t to_copy = std::min(count, segment_out_capacity);

  for (size_t i = 0; i < to_copy; ++i) {
    segment_out[i] = audio[start_sample + i];
  }

  return to_copy;
}

}  // namespace dsp