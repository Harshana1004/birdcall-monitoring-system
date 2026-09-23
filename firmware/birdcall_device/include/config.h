#pragma once

#include <cstdint>

// ============================================================
// Audio capture
// ============================================================

constexpr uint32_t SAMPLE_RATE_HZ = 16000;

// INMP441 I2S pins (ESP32-S3-DevKitC-1). Not strapping, USB-JTAG
// (19/20), UART0 (43/44) or octal-PSRAM (35-37) pins.
constexpr int I2S_MIC_SCK_PIN = 4;  // bit clock (BCLK)
constexpr int I2S_MIC_WS_PIN  = 5;  // word select (LRCLK)
constexpr int I2S_MIC_SD_PIN  = 6;  // serial data from mic

// false: INMP441 L/R tied to GND (left slot). true: L/R tied to 3V3.
// If the level meter shows only zeros, flip this first.
constexpr bool I2S_MIC_CHANNEL_RIGHT = false;

// One-pole DC-blocking high-pass applied to raw mic samples in the
// capture layer (before the DSP pipeline), removing the INMP441's
// DC offset and sub-audio drift. 0 disables it.
constexpr float MIC_DC_BLOCK_CUTOFF_HZ = 20.0f;

// ============================================================
// Short-time energy / ROI detection
// ============================================================

constexpr float FRAME_DURATION_SECONDS = 0.025f;
constexpr float HOP_DURATION_SECONDS   = 0.010f;

constexpr uint32_t FRAME_LENGTH_SAMPLES =
    static_cast<uint32_t>(FRAME_DURATION_SECONDS * SAMPLE_RATE_HZ);   // 400

constexpr uint32_t HOP_LENGTH_SAMPLES =
    static_cast<uint32_t>(HOP_DURATION_SECONDS * SAMPLE_RATE_HZ);     // 160

// smooth_energy(window_size=15) in the reference implementation.
constexpr uint32_t ENERGY_SMOOTHING_WINDOW = 15;

// calculate_threshold: threshold = median(smoothed_energy) * factor
constexpr float ROI_THRESHOLD_FACTOR = 2.0f;

// _filter_and_pad_regions
constexpr float ROI_MIN_DURATION_SECONDS = 0.30f;
constexpr float ROI_MERGE_GAP_SECONDS    = 0.50f;
constexpr float ROI_PADDING_SECONDS      = 0.25f;

// ============================================================
// High-pass filter
// ============================================================

constexpr float HIGHPASS_CUTOFF_HZ = 1000.0f;
constexpr uint32_t HIGHPASS_FILTER_ORDER = 4;

// ============================================================
// Buffer sizing
// ============================================================

constexpr uint32_t MAX_CAPTURE_SECONDS = 30;
constexpr uint32_t MAX_CAPTURE_SAMPLES = MAX_CAPTURE_SECONDS * SAMPLE_RATE_HZ;