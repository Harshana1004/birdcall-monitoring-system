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

// Backend reached over 4G (plain HTTP): the Azure VM "birdcall-server"
// (static public IP; deployed with deploy/setup_server.sh).
constexpr const char* BACKEND_HOST = "70.153.140.247";
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

// calculate_threshold: threshold = median(smoothed_energy) * factor.
// Marks where a region starts and ends.
constexpr float ROI_THRESHOLD_FACTOR = 2.0f;

// Peak gate (edge-only; not in the Python reference). Energy is
// measured after the 1 kHz high-pass, and a merged region is kept
// only if its loudest smoothed frame reaches BOTH:
//   - ROI_MIN_PEAK_FACTOR x the window's median (4 = ~6 dB above
//     the noise; 2 = no gate beyond the 2 x median threshold, which
//     alone triggers on noise fluctuations in quiet places; 8 was
//     too strict for busy soundscapes: on the Western Amazon
//     evaluation it kept 1.6 min of audio per hour vs 5.8 at 4 and
//     12 at 2, with recall falling accordingly),
//   - ROI_MIN_PEAK_DBFS, an absolute level before normalization
//     (mean-square energy, full scale = 1.0, so a full-scale sine is
//     -3 dBFS), so near-silent windows produce nothing.
// Tune both from the "levels" part of the 60 s status line: set the
// floor a few dB above the noise-floor range you see with no birds.
constexpr float ROI_MIN_PEAK_FACTOR = 4.0f;
constexpr float ROI_MIN_PEAK_DBFS = -80.0f;

// _filter_and_pad_regions
constexpr float ROI_MIN_DURATION_SECONDS = 0.30f;
constexpr float ROI_MERGE_GAP_SECONDS    = 0.50f;
constexpr float ROI_PADDING_SECONDS      = 0.25f;

// ============================================================
// High-pass filter (ROI detection only; uploads are unfiltered)
// ============================================================

constexpr float HIGHPASS_CUTOFF_HZ = 1000.0f;
constexpr uint32_t HIGHPASS_FILTER_ORDER = 4;

// ============================================================
// Buffer sizing
// ============================================================

constexpr uint32_t MAX_CAPTURE_SECONDS = 30;
constexpr uint32_t MAX_CAPTURE_SAMPLES = MAX_CAPTURE_SECONDS * SAMPLE_RATE_HZ;

// ============================================================
// Continuous monitoring (app/monitor.cpp)
// ============================================================

// Audio is processed in back-to-back windows of this length; the
// DSP threshold adapts per window. A call crossing a window edge is
// detected as two ROIs (one per window).
constexpr uint32_t CAPTURE_WINDOW_SECONDS = 10;

// A capture session (capture_session_id) is one stretch of
// gap-free audio; a new one starts after this long, or after any
// lost audio, keeping ROI times small and meaningful.
constexpr uint32_t SESSION_MAX_SECONDS = 3600;

// Upload queue in PSRAM: ROI audio waiting for the network, as PCM16.
// 4 MB = ~131 s of ROI audio; ROIs that do not fit are dropped and
// counted.
constexpr size_t UPLOAD_QUEUE_POOL_BYTES = 4 * 1024 * 1024;
constexpr size_t UPLOAD_QUEUE_MAX_ENTRIES = 256;

// Retry back-off for uploads that fail on the network side.
constexpr uint32_t UPLOAD_RETRY_INITIAL_MS = 5000;
constexpr uint32_t UPLOAD_RETRY_MAX_MS = 120000;

// true: upload over 4G via the A7670 to BACKEND_HOST (field).
// false: via the USB serial bridge, tools/serial_bridge.py (bench;
// the bridge must then post to a backend that knows DEVICE_ID, e.g.
// --backend http://70.153.140.247:8000).
constexpr bool UPLOAD_VIA_MODEM = true;

// ============================================================
// Upload (POST /api/v1/recordings)
// ============================================================

// Sent as edge_processing_version with every ROI. Bump whenever
// the on-device processing changes in a way that affects output.
constexpr const char* EDGE_PROCESSING_VERSION = "esp32-dsp-1.2.0";

// UUID of this device's row in the backend's devices table
// (POST /api/v1/devices returns it). Not secret. This is ESP32-DEV-01
// on the Azure backend; the laptop backend's row has a different id
// (ab76366d-fdb3-4225-972a-8edf737dac99).
constexpr const char* DEVICE_ID = "a7e554f5-a5af-4471-8f76-3b4ebd945395";  // ESP32-DEV-01
