#include <Arduino.h>

#include <cmath>
#include <cstring>

#include <esp_random.h>

#include "audio/audio_capture.h"
#include "bridge/serial_bridge.h"
#include "config.h"
#include "dsp/dsp_pipeline.h"
#include "upload/edge_metadata.h"
#include "upload/roi_upload.h"
#include "upload/uuid.h"
#include "modem/a7670.h"
#include "util/clock.h"

// ============================================================
// Firmware status: bench prototype (capture, DSP, upload via bridge).
// ============================================================
//
// loop() prints a live mic level meter every 100 ms, for checking
// the wiring. Pressing the BOOT button records kTestCaptureSeconds
// of real audio into PSRAM and runs the full DSP pipeline over it.
//
// Serial commands:
//   'd'  same capture, but first quantizes it to PCM16 and streams it
//        as base64 so tools/capture_wav.py can save it as a WAV (the
//        pipeline then runs on exactly the dumped samples)
//   'u'  same capture, then uploads every ROI to the backend through
//        tools/serial_bridge.py (bench stand-in for the modem)
//   'g'  same capture, then uploads every ROI over 4G via the A7670
//        to BACKEND_HOST
//   'n'  4G network check: registration, data, NTP, HTTP GET
//   'r'  raw I2S bit-alignment check
//   'm'  modem passthrough: each line typed is sent to the A7670 as an
//        AT command, modem output is echoed; type "exit" to leave
//   't<unix_ms>'  set the clock (sent by the bridge)

namespace {

constexpr int kBootButtonPin = 0;  // BOOT button, active low
constexpr uint32_t kTestCaptureSeconds = 10;
constexpr size_t kTestCaptureSamples = kTestCaptureSeconds * SAMPLE_RATE_HZ;
constexpr size_t kMeterBlockSamples = SAMPLE_RATE_HZ / 10;  // 100 ms
constexpr size_t kMaxRegions = 64;

float meter_block[kMeterBlockSamples];

// Logs every AT exchange to the USB serial port.
modem::A7670 modem_link(Serial1, &Serial);

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

// Streams the capture as little-endian PCM16, base64, framed by
// BEGIN_WAV / END_WAV. Quantizes `samples` in place to the dumped
// values.
void dump_pcm16(float* samples, size_t count) {
  Serial.printf("BEGIN_WAV %u %u\n", static_cast<unsigned>(SAMPLE_RATE_HZ),
                static_cast<unsigned>(count));

  bridge::Base64SerialSink sink;
  for (size_t i = 0; i < count; ++i) {
    const int16_t q = to_pcm16(samples[i]);
    samples[i] = q / 32768.0f;
    const uint8_t bytes[2] = {static_cast<uint8_t>(q & 0xFF),
                              static_cast<uint8_t>((q >> 8) & 0xFF)};
    sink.write(bytes, sizeof(bytes));
  }
  sink.finish();

  Serial.println("END_WAV");
}

void new_uuid(char* out) {
  // With WiFi/BT off the hardware RNG runs as a CSPRNG seeded from
  // boot-time entropy, which is ample for UUIDs.
  uint8_t bytes[16];
  esp_fill_random(bytes, sizeof(bytes));
  upload::format_uuid_v4(bytes, out);
}

enum class Transport { kSerialBridge, kModem };

// Brings the A7670 up to a usable data connection and, if the clock
// is not set yet, sets it from NTP. Safe to call repeatedly.
bool ensure_modem_ready() {
  if (!modem_link.probe(10000)) {
    Serial.println("modem: no answer to AT -- check wiring and power");
    return false;
  }
  if (!modem_link.wait_for_network(60000)) {
    Serial.println("modem: not registered on the network");
    return false;
  }
  if (!modem_link.open_data()) {
    Serial.println("modem: could not open the data connection");
    return false;
  }
  if (!util::clock_is_set()) {
    int64_t unix_ms = 0;
    if (!modem_link.sync_time(&unix_ms)) {
      Serial.println("modem: NTP time sync failed");
      return false;
    }
    util::set_clock_unix_ms(unix_ms);
    char iso[upload::kIso8601Length + 1];
    upload::format_iso8601_utc(unix_ms, iso);
    Serial.printf("modem: clock set to %s\n", iso);
  }
  return true;
}

// 'n': checks modem, registration, data, NTP and a plain-HTTP GET.
void run_network_check() {
  Serial.println("\nNetwork check (modem log follows)...");
  if (!ensure_modem_ready()) {
    Serial.println("Network check FAILED.\n");
    return;
  }
  const int status = modem_link.http_get(NETWORK_CHECK_HOST,
                                         NETWORK_CHECK_PORT, "/");
  Serial.printf("GET http://%s/ -> %d\n", NETWORK_CHECK_HOST, status);
  Serial.println(status == 200 ? "Network check OK.\n"
                               : "Network check FAILED at the HTTP step.\n");
}

// Uploads every ROI of one processed capture, through the serial
// bridge or the A7670. Each ROI keeps its client_upload_id across
// retries, so a retry after a lost response is recognised by the
// backend (200).
void upload_rois(const dsp::PipelineResult& result, int64_t started_unix_ms,
                 Transport transport) {
  constexpr int kMaxAttempts = 3;
  constexpr uint32_t kResponseTimeoutMs = 30000;

  char metadata[1024];
  if (upload::format_edge_metadata(metadata, sizeof(metadata), result) == 0) {
    Serial.println("upload: metadata buffer too small");
    return;
  }

  char started_at[upload::kIso8601Length + 1];
  upload::format_iso8601_utc(started_unix_ms, started_at);

  char session_id[upload::kUuidStringLength + 1];
  new_uuid(session_id);
  Serial.printf("upload: session %s, started %s, %u ROI(s)\n", session_id,
                started_at, static_cast<unsigned>(result.roi_count));

  for (size_t i = 0; i < result.roi_count; ++i) {
    char upload_id[upload::kUuidStringLength + 1];
    new_uuid(upload_id);

    const upload::RoiUploadFields fields{
        DEVICE_ID,
        upload_id,
        session_id,
        static_cast<uint32_t>(i),
        started_at,
        rois[i].region.start_time_seconds,
        rois[i].region.end_time_seconds,
        EDGE_PROCESSING_VERSION,
        metadata};

    int status = 0;
    for (int attempt = 1; attempt <= kMaxAttempts; ++attempt) {
      const uint32_t attempt_started = millis();
      if (transport == Transport::kSerialBridge) {
        status = bridge::send_upload(fields, rois[i].audio,
                                     rois[i].sample_count, SAMPLE_RATE_HZ,
                                     kResponseTimeoutMs);
      } else {
        status = modem_link.post_roi(BACKEND_HOST, BACKEND_PORT,
                                     BACKEND_UPLOAD_PATH, fields,
                                     rois[i].audio, rois[i].sample_count,
                                     SAMPLE_RATE_HZ);
      }
      Serial.printf("upload: roi %u attempt %d -> %d (%.1f s)\n",
                    static_cast<unsigned>(i), attempt, status,
                    (millis() - attempt_started) / 1000.0f);
      if (status == 200 || status == 201) {
        break;
      }
      // 4xx other than timeouts won't succeed on retry.
      if (status >= 400 && status < 500 && status != 408 && status != 429) {
        break;
      }
      // A transport failure may have left the data connection down.
      if (transport == Transport::kModem && status < 0) {
        ensure_modem_ready();
      }
    }
  }
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

enum class CaptureMode { kPrintOnly, kDumpWav, kUploadBridge, kUploadModem };

void run_test_capture(CaptureMode mode) {
  if (mode == CaptureMode::kUploadBridge && !util::clock_is_set() &&
      !bridge::request_time(3000)) {
    Serial.println("upload: clock not set -- run tools/serial_bridge.py");
    return;
  }
  // Bring the modem up before recording, so the capture timestamp
  // comes from NTP and the upload can start straight away.
  if (mode == CaptureMode::kUploadModem && !ensure_modem_ready()) {
    Serial.println("upload: modem not ready\n");
    return;
  }

  Serial.printf("\nRecording %u s -- make some noise...\n",
                static_cast<unsigned>(kTestCaptureSeconds));

  const int64_t started_unix_ms = util::now_unix_ms();
  const size_t got = audio::read(capture, kTestCaptureSamples);
  const BlockStats raw = measure(capture, got);
  Serial.printf("Captured %u samples: rms %.1f dBFS, peak %.1f dBFS, dc %+.5f\n",
                static_cast<unsigned>(got), to_dbfs(raw.rms),
                to_dbfs(raw.peak), raw.dc);

  if (mode == CaptureMode::kDumpWav) {
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

  if (mode == CaptureMode::kUploadBridge) {
    upload_rois(result, started_unix_ms, Transport::kSerialBridge);
  } else if (mode == CaptureMode::kUploadModem) {
    upload_rois(result, started_unix_ms, Transport::kModem);
  }
  Serial.println("Back to level meter.\n");
}

// Bring-up helper: forwards typed lines to the modem as AT commands
// (terminated with CR) and echoes everything the modem sends back.
// Line-based so the PlatformIO monitor works as-is.
void run_modem_passthrough() {
  Serial.println("\nModem passthrough. Type AT commands; \"exit\" to leave.");
  Serial.printf("(UART1 %u baud, ESP TX=GPIO%d -> modem RX, "
                "ESP RX=GPIO%d <- modem TX)\n",
                static_cast<unsigned>(MODEM_BAUD), MODEM_TX_PIN,
                MODEM_RX_PIN);

  char line[256];
  size_t length = 0;

  while (true) {
    while (Serial1.available() > 0) {
      Serial.write(static_cast<uint8_t>(Serial1.read()));
    }

    while (Serial.available() > 0) {
      const char c = static_cast<char>(Serial.read());
      if (c == '\r' || c == '\n') {
        if (length == 0) {
          continue;
        }
        line[length] = '\0';
        length = 0;
        if (strcmp(line, "exit") == 0) {
          Serial.println("Leaving passthrough. Back to level meter.\n");
          // Drop audio buffered while we were away from the meter.
          audio::read(meter_block, kMeterBlockSamples);
          return;
        }
        Serial1.print(line);
        Serial1.print('\r');
      } else if (length + 1 < sizeof(line)) {
        line[length++] = c;
      }
    }

    delay(1);
  }
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

  Serial1.begin(MODEM_BAUD, SERIAL_8N1, MODEM_RX_PIN, MODEM_TX_PIN);

  if (!audio::begin()) {
    Serial.println("I2S driver install failed");
    while (true) delay(1000);
  }

  Serial.println("Mic running. Press BOOT for a test capture; send 'd' "
                 "(dump WAV), 'u' (upload via bridge), 'g' (upload via 4G), "
                 "'n' (4G network check), 'r' (raw bits) or 'm' (modem AT "
                 "passthrough).\n");
}

void loop() {
  if (Serial.available() > 0) {
    const int command = Serial.read();
    if (command == 'd') {
      run_test_capture(CaptureMode::kDumpWav);
      return;
    }
    if (command == 'u') {
      run_test_capture(CaptureMode::kUploadBridge);
      return;
    }
    if (command == 'g') {
      run_test_capture(CaptureMode::kUploadModem);
      return;
    }
    if (command == 'n') {
      run_network_check();
      return;
    }
    if (command == 't') {
      char line[32] = "t";
      bridge::read_line(line + 1, sizeof(line) - 1, 500);
      if (bridge::apply_time_command(line)) {
        Serial.println("clock set");
      }
      return;
    }
    if (command == 'r') {
      run_raw_bit_check();
      return;
    }
    if (command == 'm') {
      run_modem_passthrough();
      return;
    }
  }

  if (digitalRead(kBootButtonPin) == LOW) {
    run_test_capture(CaptureMode::kPrintOnly);
    while (digitalRead(kBootButtonPin) == LOW) delay(10);
    return;
  }

  audio::read(meter_block, kMeterBlockSamples);
  print_meter(measure(meter_block, kMeterBlockSamples));
}
