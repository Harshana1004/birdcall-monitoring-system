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
// Cellular modem (SIMCom A7670C, FS-MCore V1.2 board)
// ============================================================

// UART1 to the modem. ESP TX -> modem RX, ESP RX <- modem TX.
constexpr int MODEM_TX_PIN = 17;
constexpr int MODEM_RX_PIN = 18;
constexpr uint32_t MODEM_BAUD = 115200;  // A7670 factory default

// Backend reached over 4G (plain HTTP). Must be internet-reachable:
// set this to the Oracle Cloud VM's public IP once it exists.
constexpr const char* BACKEND_HOST = "0.0.0.0";
constexpr uint16_t BACKEND_PORT = 8000;
constexpr const char* BACKEND_UPLOAD_PATH = "/api/v1/recordings";

// Plain-HTTP site used by the 'n' network check to prove the SIM's
// data connection reaches the internet.
constexpr const char* NETWORK_CHECK_HOST = "example.com";
constexpr uint16_t NETWORK_CHECK_PORT = 80;

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

// ============================================================
// Upload (POST /api/v1/recordings)
// ============================================================

// Sent as edge_processing_version with every ROI. Bump whenever
// the on-device processing changes in a way that affects output.
constexpr const char* EDGE_PROCESSING_VERSION = "esp32-dsp-1.0.0";

// UUID of this device's row in the backend's devices table
// (POST /api/v1/devices returns it). Not secret.
constexpr const char* DEVICE_ID = "ab76366d-fdb3-4225-972a-8edf737dac99";  // ESP32-DEV-01
