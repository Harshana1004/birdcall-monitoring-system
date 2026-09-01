#pragma once

#include <cstdint>

// ============================================================
// Audio capture
// ============================================================

constexpr uint32_t SAMPLE_RATE_HZ = 16000;

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