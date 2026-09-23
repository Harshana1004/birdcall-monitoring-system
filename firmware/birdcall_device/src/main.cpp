#include <Arduino.h>

#include <cmath>

#include "audio/audio_capture.h"
#include "config.h"
#include "dsp/dsp_pipeline.h"

// ============================================================
// Firmware status: INMP441 bring-up.
// ============================================================
//
// loop() prints a live mic level meter every 100 ms, for checking
// the wiring. Pressing the BOOT button records kTestCaptureSeconds
// of real audio into PSRAM and runs the full DSP pipeline over it.
//
// Sending 'd' over serial does the same, but first quantizes the
// capture to PCM16 and streams it as base64 so
// tools/capture_wav.py can save it as a WAV (the pipeline then runs
// on exactly the dumped samples, for comparison with the backend).
//
// The A7670 upload path is not wired in yet.

namespace {

constexpr int kBootButtonPin = 0;  // BOOT button, active low
constexpr uint32_t kTestCaptureSeconds = 10;
constexpr size_t kTestCaptureSamples = kTestCaptureSeconds * SAMPLE_RATE_HZ;
constexpr size_t kMeterBlockSamples = SAMPLE_RATE_HZ / 10;  // 100 ms
constexpr size_t kMaxRegions = 64;

float meter_block[kMeterBlockSamples];

float* capture = nullptr;
float* energy = nullptr;
float* smoothed = nullptr;
float* arena = nullptr;
dsp::RegionOfInterest* regions = nullptr;
dsp::ProcessedRoi rois[kMaxRegions];
size_t frame_capacity = 0;

template <typename T>
T* psram_alloc(size_t count) {
  return static_cast<T*>(
      heap_caps_malloc(count * sizeof(T), MALLOC_CAP_SPIRAM));
}

float to_dbfs(float linear) {
  return linear > 0.0f ? 20.0f * log10f(linear) : -120.0f;
}

struct BlockStats {
  float dc;
  float rms;   // DC removed
  float peak;  // raw, including DC
};

BlockStats measure(const float* samples, size_t count) {
  double sum = 0.0;
  float peak = 0.0f;
  for (size_t i = 0; i < count; ++i) {
    sum += samples[i];
    peak = fmaxf(peak, fabsf(samples[i]));
  }
  const float dc = static_cast<float>(sum / count);

  double sum_sq = 0.0;
  for (size_t i = 0; i < count; ++i) {
    const double centered = samples[i] - dc;
    sum_sq += centered * centered;
  }
  return BlockStats{dc, static_cast<float>(sqrt(sum_sq / count)), peak};
}

void print_meter(const BlockStats& s) {
  // Bar spans -90 dBFS (empty) to -10 dBFS (full), 2 dB per char.
  const float db = to_dbfs(s.rms);
  int bars = static_cast<int>((db + 90.0f) / 2.0f);
  bars = bars < 0 ? 0 : (bars > 40 ? 40 : bars);

  char bar[41];
  for (int i = 0; i < 40; ++i) {
    bar[i] = i < bars ? '#' : '.';
  }
  bar[40] = '\0';

  Serial.printf("rms %6.1f dBFS  peak %6.1f dBFS  dc %+.5f  |%s|\n", db,
                to_dbfs(s.peak), s.dc, bar);
}

int16_t to_pcm16(float sample) {
  const float scaled = roundf(sample * 32768.0f);
  return static_cast<int16_t>(fmaxf(-32768.0f, fminf(32767.0f, scaled)));
}

// Streams the capture as little-endian PCM16, base64, 76 chars per
// line, framed by BEGIN_WAV / END_WAV. Quantizes `samples` in place
// to the dumped values.
void dump_pcm16(float* samples, size_t count) {
  static const char kAlphabet[] =
      "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

  Serial.printf("BEGIN_WAV %u %u\n", static_cast<unsigned>(SAMPLE_RATE_HZ),
                static_cast<unsigned>(count));

  uint8_t bytes[57];  // 57 bytes -> 76 base64 chars
  char line[77];
  size_t filled = 0;

  auto flush = [&]() {
    size_t out = 0;
    for (size_t i = 0; i < filled; i += 3) {
      const uint32_t b0 = bytes[i];
      const uint32_t b1 = i + 1 < filled ? bytes[i + 1] : 0;
      const uint32_t b2 = i + 2 < filled ? bytes[i + 2] : 0;
      const uint32_t v = (b0 << 16) | (b1 << 8) | b2;
      line[out++] = kAlphabet[(v >> 18) & 63];
      line[out++] = kAlphabet[(v >> 12) & 63];
      line[out++] = i + 1 < filled ? kAlphabet[(v >> 6) & 63] : '=';
      line[out++] = i + 2 < filled ? kAlphabet[v & 63] : '=';
    }
    line[out] = '\0';
    Serial.println(line);
    filled = 0;
  };

  for (size_t i = 0; i < count; ++i) {
    const int16_t q = to_pcm16(samples[i]);
    samples[i] = q / 32768.0f;
    bytes[filled++] = static_cast<uint8_t>(q & 0xFF);
    bytes[filled++] = static_cast<uint8_t>((q >> 8) & 0xFF);
    if (filled == 54) {  // multiple of both 2 and 3: no padding mid-stream
      flush();
    }
  }
  if (filled > 0) {
    flush();
  }

  Serial.println("END_WAV");
}

// Reports where the mic's data bits sit inside the 32-bit I2S slot.
// Correctly aligned 24-bit data: lowest set bit is always >= 8, and
// the top bits only all equal the sign bit when the signal is small.
void run_raw_bit_check() {
  constexpr size_t kSlots = 3 * SAMPLE_RATE_HZ;
  int32_t* slots = psram_alloc<int32_t>(kSlots);
  if (slots == nullptr) {
    Serial.println("raw check: allocation failed");
    return;
  }

  Serial.println("\nRaw bit check: recording 3 s -- clap loudly near the mic...");
  const size_t got = audio::read_raw_slots(slots, kSlots);

  uint32_t lowest_bit_hist[32] = {};
  uint32_t zero_slots = 0;
  uint32_t no_headroom = 0;  // bit 30 differs from sign bit 31
  int32_t min_slot = INT32_MAX;
  int32_t max_slot = INT32_MIN;
  uint32_t big_jumps = 0;    // consecutive samples differ by > 1.5 x 2^31

  for (size_t i = 0; i < got; ++i) {
    const int32_t s = slots[i];
    if (s == 0) {
      ++zero_slots;
    } else {
      ++lowest_bit_hist[__builtin_ctz(static_cast<uint32_t>(s))];
    }
    if (((s >> 31) & 1) != ((s >> 30) & 1)) {
      ++no_headroom;
    }
    min_slot = s < min_slot ? s : min_slot;
    max_slot = s > max_slot ? s : max_slot;
    if (i > 0) {
      const int64_t step = static_cast<int64_t>(s) - slots[i - 1];
      if (step > 3221225472LL || step < -3221225472LL) {
        ++big_jumps;
      }
    }
  }

  Serial.printf("slots=%u zero=%u min=0x%08X max=0x%08X\n",
                static_cast<unsigned>(got), static_cast<unsigned>(zero_slots),
                static_cast<unsigned>(min_slot), static_cast<unsigned>(max_slot));
  Serial.printf("slots using top bit (bit30 != bit31): %u, near full-scale "
                "sign flips between samples: %u\n",
                static_cast<unsigned>(no_headroom),
                static_cast<unsigned>(big_jumps));
  Serial.print("lowest set bit histogram (bit:count):");
  for (int b = 0; b < 32; ++b) {
    if (lowest_bit_hist[b] > 0) {
      Serial.printf(" %d:%u", b, static_cast<unsigned>(lowest_bit_hist[b]));
    }
  }
  Serial.println();

  Serial.print("first 8 slots:");
  for (size_t i = 0; i < 8 && i < got; ++i) {
    Serial.printf(" %08X", static_cast<unsigned>(slots[i]));
  }
  Serial.println("\nBack to level meter.\n");

  heap_caps_free(slots);
}

void run_test_capture(bool dump) {
  Serial.printf("\nRecording %u s -- make some noise...\n",
                static_cast<unsigned>(kTestCaptureSeconds));

  const size_t got = audio::read(capture, kTestCaptureSamples);
  const BlockStats raw = measure(capture, got);
  Serial.printf("Captured %u samples: rms %.1f dBFS, peak %.1f dBFS, dc %+.5f\n",
                static_cast<unsigned>(got), to_dbfs(raw.rms),
                to_dbfs(raw.peak), raw.dc);

  if (dump) {
    dump_pcm16(capture, got);
  }

  const dsp::PipelineWorkspace workspace{energy, smoothed, frame_capacity,
                                         regions, kMaxRegions, arena,
                                         kTestCaptureSamples};

  const uint32_t started_us = micros();
  const dsp::PipelineResult result =
      dsp::process_capture(capture, got, workspace, rois, kMaxRegions);
  const uint32_t elapsed_us = micros() - started_us;

  Serial.printf("status=%d frames=%u threshold=%.6g rois=%u (%.1f ms)\n",
                static_cast<int>(result.status),
                static_cast<unsigned>(result.frame_count),
                result.energy_threshold,
                static_cast<unsigned>(result.roi_count),
                elapsed_us / 1000.0f);

  for (size_t i = 0; i < result.roi_count; ++i) {
    Serial.printf("  roi %u: %.3f s -> %.3f s (%u samples)\n",
                  static_cast<unsigned>(rois[i].index),
                  rois[i].region.start_time_seconds,
                  rois[i].region.end_time_seconds,
                  static_cast<unsigned>(rois[i].sample_count));
  }
  Serial.println("Back to level meter.\n");
}

}  // namespace

void setup() {
  Serial.begin(115200);
  delay(1000);

  Serial.println("BirdCall edge firmware -- INMP441 bring-up");
  Serial.printf("PSRAM: %u bytes free\n",
                static_cast<unsigned>(ESP.getFreePsram()));

  pinMode(kBootButtonPin, INPUT_PULLUP);

  frame_capacity = dsp::pipeline_frame_count(kTestCaptureSamples);
  capture = psram_alloc<float>(kTestCaptureSamples);
  energy = psram_alloc<float>(frame_capacity);
  smoothed = psram_alloc<float>(frame_capacity);
  arena = psram_alloc<float>(kTestCaptureSamples);
  regions = psram_alloc<dsp::RegionOfInterest>(kMaxRegions);

  if (!capture || !energy || !smoothed || !arena || !regions) {
    Serial.println("PSRAM allocation failed");
    while (true) delay(1000);
  }

  if (!audio::begin()) {
    Serial.println("I2S driver install failed");
    while (true) delay(1000);
  }

  Serial.println("Mic running. Press BOOT (or send 'd' to also dump a WAV) "
                 "for a test capture.\n");
}

void loop() {
  if (Serial.available() > 0) {
    const int command = Serial.read();
    if (command == 'd') {
      run_test_capture(true);
      return;
    }
    if (command == 'r') {
      run_raw_bit_check();
      return;
    }
  }

  if (digitalRead(kBootButtonPin) == LOW) {
    run_test_capture(false);
    while (digitalRead(kBootButtonPin) == LOW) delay(10);
    return;
  }

  audio::read(meter_block, kMeterBlockSamples);
  print_meter(measure(meter_block, kMeterBlockSamples));
}
