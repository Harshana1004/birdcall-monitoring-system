#include "upload/wav_writer.h"

#include <cmath>

namespace upload {

namespace {

void put_u16(uint8_t* p, uint16_t v) {
  p[0] = static_cast<uint8_t>(v & 0xFF);
  p[1] = static_cast<uint8_t>(v >> 8);
}

void put_u32(uint8_t* p, uint32_t v) {
  p[0] = static_cast<uint8_t>(v & 0xFF);
  p[1] = static_cast<uint8_t>((v >> 8) & 0xFF);
  p[2] = static_cast<uint8_t>((v >> 16) & 0xFF);
  p[3] = static_cast<uint8_t>(v >> 24);
}

}  // namespace

void write_wav_header(uint8_t out[kWavHeaderBytes], uint32_t sample_count,
                      uint32_t sample_rate) {
  constexpr uint16_t kChannels = 1;
  constexpr uint16_t kBitsPerSample = 16;
  constexpr uint16_t kBlockAlign = kChannels * kBitsPerSample / 8;
  const uint32_t data_bytes = sample_count * kBlockAlign;

  out[0] = 'R'; out[1] = 'I'; out[2] = 'F'; out[3] = 'F';
  put_u32(out + 4, 36 + data_bytes);
  out[8] = 'W'; out[9] = 'A'; out[10] = 'V'; out[11] = 'E';

  out[12] = 'f'; out[13] = 'm'; out[14] = 't'; out[15] = ' ';
  put_u32(out + 16, 16);          // fmt chunk size
  put_u16(out + 20, 1);           // PCM
  put_u16(out + 22, kChannels);
  put_u32(out + 24, sample_rate);
  put_u32(out + 28, sample_rate * kBlockAlign);  // byte rate
  put_u16(out + 32, kBlockAlign);
  put_u16(out + 34, kBitsPerSample);

  out[36] = 'd'; out[37] = 'a'; out[38] = 't'; out[39] = 'a';
  put_u32(out + 40, data_bytes);
}

void encode_pcm16(const float* samples, size_t count, uint8_t* out) {
  for (size_t i = 0; i < count; ++i) {
    float scaled = std::nearbyint(samples[i] * 32768.0f);
    scaled = scaled > 32767.0f ? 32767.0f : scaled;
    scaled = scaled < -32768.0f ? -32768.0f : scaled;
    const int16_t q = static_cast<int16_t>(scaled);
    put_u16(out + 2 * i, static_cast<uint16_t>(q));
  }
}

}  // namespace upload
