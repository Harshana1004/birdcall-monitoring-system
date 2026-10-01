#pragma once

#include <cstddef>
#include <cstdint>

namespace upload {

constexpr size_t kWavHeaderBytes = 44;

// Writes a canonical 44-byte RIFF/WAVE header for mono 16-bit PCM
// holding `sample_count` samples.
void write_wav_header(uint8_t out[kWavHeaderBytes], uint32_t sample_count,
                      uint32_t sample_rate);

// Converts one float sample in [-1, 1] to PCM16 (round-to-nearest,
// clamped). encode_pcm16 uses exactly this conversion.
int16_t to_pcm16(float sample);

// Converts float samples in [-1, 1] to little-endian PCM16
// (round-to-nearest, clamped), writing 2 * count bytes to `out`.
// Uses the same 32768 scale as the serial WAV dump in main.cpp.
void encode_pcm16(const float* samples, size_t count, uint8_t* out);

inline size_t wav_file_bytes(uint32_t sample_count) {
  return kWavHeaderBytes + static_cast<size_t>(sample_count) * 2;
}

}  // namespace upload
