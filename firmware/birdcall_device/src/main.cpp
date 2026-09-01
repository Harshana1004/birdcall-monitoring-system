#include <Arduino.h>

#include "config.h"
#include "dsp/energy.h"
#include "dsp/normalize.h"
#include "dsp/roi_detector.h"
#include "dsp/smoothing.h"

// ============================================================
// Firmware status: DSP core only.
// ============================================================
//
// Audio capture (I2S / INMP441), the high-pass filter,
// segmentation, and the A7670 cellular upload path are not yet
// wired in here -- they are being built and verified as separate
// modules first (see src/dsp/, and upcoming src/audio/,
// src/cellular/). This file will become the real capture ->
// detect -> extract -> filter -> upload state machine once those
// pieces exist.
//
// For now, setup()/loop() just confirm the DSP core links and
// runs on-device, using a tiny synthetic buffer, as a smoke test
// distinct from the desktop verification harness in test/.

void setup() {
  Serial.begin(115200);
  delay(1000);

  Serial.println("BirdCall edge firmware -- DSP core smoke test");

  constexpr size_t kSampleCount = SAMPLE_RATE_HZ;  // 1 second
  float* audio = static_cast<float*>(
      heap_caps_malloc(kSampleCount * sizeof(float), MALLOC_CAP_SPIRAM));

  if (audio == nullptr) {
    Serial.println("PSRAM allocation failed -- check board_build.arduino.memory_type");
    return;
  }

  for (size_t i = 0; i < kSampleCount; ++i) {
    audio[i] = 0.01f * sinf(2.0f * PI * 440.0f * i / SAMPLE_RATE_HZ);
  }

  dsp::normalize_audio_in_place(audio, kSampleCount);

  const size_t frame_count = dsp::short_time_energy_frame_count(
      kSampleCount, FRAME_LENGTH_SAMPLES, HOP_LENGTH_SAMPLES);

  float* energy = static_cast<float*>(
      heap_caps_malloc(frame_count * sizeof(float), MALLOC_CAP_SPIRAM));

  dsp::compute_short_time_energy(audio, kSampleCount, FRAME_LENGTH_SAMPLES,
                                  HOP_LENGTH_SAMPLES, energy, frame_count);

  Serial.printf("Computed %u energy frames from %u samples\n",
                static_cast<unsigned>(frame_count),
                static_cast<unsigned>(kSampleCount));

  heap_caps_free(audio);
  heap_caps_free(energy);
}

void loop() {
  delay(10000);
}