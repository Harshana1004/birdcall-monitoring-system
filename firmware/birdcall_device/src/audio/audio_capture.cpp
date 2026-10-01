#include "audio/audio_capture.h"

#include <driver/i2s.h>

#include <cmath>

#include "config.h"

namespace audio {

namespace {

constexpr i2s_port_t kPort = I2S_NUM_0;

// DMA: 16 x 256 frames = 256 ms of buffering at 16 kHz, so a reader
// briefly delayed by another task does not lose audio.
constexpr int kDmaBufferCount = 16;
constexpr int kDmaBufferFrames = 256;

// Driver events; I2S_EVENT_RX_Q_OVF means DMA overwrote audio that
// had not been read yet (a gap in the stream).
constexpr int kEventQueueLength = 32;
QueueHandle_t event_queue = nullptr;
uint32_t overflows = 0;

void drain_events() {
  if (event_queue == nullptr) {
    return;
  }
  i2s_event_t event;
  while (xQueueReceive(event_queue, &event, 0) == pdTRUE) {
    if (event.type == I2S_EVENT_RX_Q_OVF) {
      ++overflows;
    }
  }
}

// Datasheet: INMP441 output is valid ~85 ms after the clock
// starts; discard a bit more to be safe.
constexpr uint32_t kStartupDiscardMs = 150;

// Raw 32-bit slots read per i2s_read() call (internal RAM).
constexpr size_t kChunkSamples = 256;
int32_t raw_chunk[kChunkSamples];

constexpr float kInt24Scale = 1.0f / 8388608.0f;  // 2^23

// DC blocker: y[n] = x[n] - x[n-1] + R * y[n-1],
// with R = 1 - 2*pi*fc/fs (-3 dB at roughly fc).
constexpr float kDcBlockR =
    1.0f - 2.0f * 3.14159265f * MIC_DC_BLOCK_CUTOFF_HZ / SAMPLE_RATE_HZ;
float dc_prev_x = 0.0f;
float dc_prev_y = 0.0f;

float dc_block(float x) {
  if (MIC_DC_BLOCK_CUTOFF_HZ <= 0.0f) {
    return x;
  }
  const float y = x - dc_prev_x + kDcBlockR * dc_prev_y;
  dc_prev_x = x;
  dc_prev_y = y;
  return y;
}

// Reads up to `count` samples (<= kChunkSamples) into raw_chunk.
size_t read_raw(size_t count) {
  size_t bytes_read = 0;
  if (i2s_read(kPort, raw_chunk, count * sizeof(int32_t), &bytes_read,
               portMAX_DELAY) != ESP_OK) {
    return 0;
  }
  return bytes_read / sizeof(int32_t);
}

// Arithmetic shift keeps the sign of the 24-bit sample.
float to_float(int32_t slot) {
  return static_cast<float>(slot >> 8) * kInt24Scale;
}

}  // namespace

bool begin() {
  const i2s_config_t config = {
      .mode = static_cast<i2s_mode_t>(I2S_MODE_MASTER | I2S_MODE_RX),
      .sample_rate = SAMPLE_RATE_HZ,
      .bits_per_sample = I2S_BITS_PER_SAMPLE_32BIT,
      .channel_format = I2S_MIC_CHANNEL_RIGHT ? I2S_CHANNEL_FMT_ONLY_RIGHT
                                              : I2S_CHANNEL_FMT_ONLY_LEFT,
      // The INMP441 is a Philips-format mic, but in STAND_I2S mode
      // the S3 receiver sampled one BCK late: the raw-bit check ('r')
      // showed the data LSB at bit 9 and the real MSB lost, so loud
      // input wrapped around. STAND_MSB samples one BCK earlier,
      // putting the 24-bit sample back at bits 31..8.
      .communication_format = I2S_COMM_FORMAT_STAND_MSB,
      .intr_alloc_flags = ESP_INTR_FLAG_LEVEL1,
      .dma_buf_count = kDmaBufferCount,
      .dma_buf_len = kDmaBufferFrames,
      .use_apll = false,
      .tx_desc_auto_clear = false,
      .fixed_mclk = 0,
  };

  const i2s_pin_config_t pins = {
      .mck_io_num = I2S_PIN_NO_CHANGE,
      .bck_io_num = I2S_MIC_SCK_PIN,
      .ws_io_num = I2S_MIC_WS_PIN,
      .data_out_num = I2S_PIN_NO_CHANGE,
      .data_in_num = I2S_MIC_SD_PIN,
  };

  if (i2s_driver_install(kPort, &config, kEventQueueLength, &event_queue) !=
      ESP_OK) {
    return false;
  }

  if (i2s_set_pin(kPort, &pins) != ESP_OK) {
    i2s_driver_uninstall(kPort);
    return false;
  }

  i2s_zero_dma_buffer(kPort);

  // Throw away the startup transient, then prime the DC blocker
  // with the next chunk so it starts settled on the mic's offset.
  size_t to_discard = SAMPLE_RATE_HZ * kStartupDiscardMs / 1000;
  while (to_discard > 0) {
    const size_t n = to_discard < kChunkSamples ? to_discard : kChunkSamples;
    const size_t got = read_raw(n);
    if (got == 0) {
      break;
    }
    to_discard -= got;
  }

  const size_t primed = read_raw(kChunkSamples);
  if (primed > 0) {
    double sum = 0.0;
    for (size_t i = 0; i < primed; ++i) {
      sum += to_float(raw_chunk[i]);
    }
    dc_prev_x = static_cast<float>(sum / primed);
    dc_prev_y = 0.0f;
    for (size_t i = 0; i < primed; ++i) {
      dc_block(to_float(raw_chunk[i]));
    }
  }

  drain_events();
  overflows = 0;  // startup reads are not part of any capture
  return true;
}

uint32_t overflow_count() {
  drain_events();
  return overflows;
}

size_t read(float* out, size_t count) {
  size_t written = 0;

  while (written < count) {
    const size_t remaining = count - written;
    const size_t n = remaining < kChunkSamples ? remaining : kChunkSamples;

    const size_t got = read_raw(n);
    if (got == 0) {
      break;
    }

    for (size_t i = 0; i < got; ++i) {
      out[written + i] = dc_block(to_float(raw_chunk[i]));
    }
    written += got;
  }

  drain_events();
  return written;
}

size_t read_raw_slots(int32_t* out, size_t count) {
  size_t written = 0;

  while (written < count) {
    const size_t remaining = count - written;
    const size_t n = remaining < kChunkSamples ? remaining : kChunkSamples;

    const size_t got = read_raw(n);
    if (got == 0) {
      break;
    }

    for (size_t i = 0; i < got; ++i) {
      out[written + i] = raw_chunk[i];
    }
    written += got;
  }

  return written;
}

void end() {
  i2s_driver_uninstall(kPort);
}

}  // namespace audio
