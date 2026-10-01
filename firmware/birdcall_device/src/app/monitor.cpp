#include "app/monitor.h"

#include <Arduino.h>
#include <esp_random.h>
#include <esp_timer.h>

#include <cstring>

#include "app/roi_queue.h"
#include "audio/audio_capture.h"
#include "config.h"
#include "dsp/dsp_pipeline.h"
#include "upload/edge_metadata.h"
#include "upload/uuid.h"
#include "upload/wav_writer.h"
#include "util/clock.h"

namespace app {

namespace {

constexpr size_t kWindowSamples =
    static_cast<size_t>(CAPTURE_WINDOW_SECONDS) * SAMPLE_RATE_HZ;
constexpr size_t kReadChunkSamples = SAMPLE_RATE_HZ / 10;  // 100 ms
constexpr size_t kMaxRoisPerWindow = 64;
constexpr uint64_t kSessionMaxSamples =
    static_cast<uint64_t>(SESSION_MAX_SECONDS) * SAMPLE_RATE_HZ;

struct Session {
  char id[upload::kUuidStringLength + 1];
  int64_t start_mono_us;  // esp_timer time of the session's first sample
};

// A captured window handed from the capture task to the process task.
struct WindowJob {
  int buffer;               // index into g_windows
  size_t samples;
  uint64_t offset_samples;  // position of the window's first sample in
                            // its session
  Session session;
};

Transport g_transport = Transport::kSerialBridge;

float* g_windows[2] = {nullptr, nullptr};
QueueHandle_t g_free_windows = nullptr;  // int: buffers free to fill
QueueHandle_t g_full_windows = nullptr;  // WindowJob: buffers to process

// DSP workspace -- used only by the process task.
float* g_energy = nullptr;
float* g_smoothed = nullptr;
size_t g_frame_capacity = 0;
dsp::RegionOfInterest* g_regions = nullptr;
size_t g_region_capacity = 0;
float* g_arena = nullptr;
dsp::ProcessedRoi g_rois[kMaxRoisPerWindow];

RoiQueue g_queue;
SemaphoreHandle_t g_queue_mutex = nullptr;
TaskHandle_t g_upload_task = nullptr;

// Written by one task each; plain 32-bit stores are atomic here, and
// the stats are informational.
MonitorStats g_stats = {};

// Capture task scratch for audio read while no window is free.
float g_discard[kReadChunkSamples];

template <typename T>
T* psram_alloc(size_t count) {
  return static_cast<T*>(
      heap_caps_malloc(count * sizeof(T), MALLOC_CAP_SPIRAM));
}

void new_uuid(char* out) {
  uint8_t bytes[16];
  esp_fill_random(bytes, sizeof(bytes));
  upload::format_uuid_v4(bytes, out);
}

// ------------------------------------------------------------
// Capture task
// ------------------------------------------------------------

void capture_task(void*) {
  Session session = {};
  uint64_t session_samples = 0;
  bool need_new_session = true;
  uint32_t overflows_seen = audio::overflow_count();

  for (;;) {
    int buffer;
    if (xQueueReceive(g_free_windows, &buffer, 0) != pdTRUE) {
      // Processing still holds both buffers. Keep draining the mic
      // so the DMA does not overflow; the audio is lost, so the next
      // window starts a new session.
      audio::read(g_discard, kReadChunkSamples);
      if (!need_new_session) {
        need_new_session = true;
        ++g_stats.windows_lost;
      }
      continue;
    }

    if (need_new_session || session_samples >= kSessionMaxSamples) {
      new_uuid(session.id);
      session.start_mono_us = 0;  // set when its first audio arrives
      session_samples = 0;
      need_new_session = false;
      ++g_stats.sessions_started;
    }

    float* window = g_windows[buffer];
    bool lost = false;
    for (size_t done = 0; done < kWindowSamples; done += kReadChunkSamples) {
      const size_t n = kWindowSamples - done < kReadChunkSamples
                           ? kWindowSamples - done
                           : kReadChunkSamples;
      audio::read(window + done, n);

      if (session.start_mono_us == 0) {
        session.start_mono_us =
            esp_timer_get_time() -
            static_cast<int64_t>(n) * 1000000 / SAMPLE_RATE_HZ;
      }

      const uint32_t overflows = audio::overflow_count();
      if (overflows != overflows_seen) {
        overflows_seen = overflows;
        lost = true;
        break;
      }
    }

    if (lost) {
      xQueueSend(g_free_windows, &buffer, 0);
      need_new_session = true;
      ++g_stats.windows_lost;
      continue;
    }

    const WindowJob job{buffer, kWindowSamples, session_samples, session};
    session_samples += kWindowSamples;
    ++g_stats.windows_captured;
    xQueueSend(g_full_windows, &job, portMAX_DELAY);
  }
}

// ------------------------------------------------------------
// Process task
// ------------------------------------------------------------

void process_task(void*) {
  char current_session[upload::kUuidStringLength + 1] = "";
  uint32_t next_sequence = 0;
  char metadata[kQueuedMetadataCapacity];

  for (;;) {
    WindowJob job;
    xQueueReceive(g_full_windows, &job, portMAX_DELAY);

    const dsp::PipelineWorkspace workspace{
        g_energy,          g_smoothed, g_frame_capacity, g_regions,
        g_region_capacity, g_arena,    kWindowSamples};
    const dsp::PipelineResult result =
        dsp::process_capture(g_windows[job.buffer], job.samples, workspace,
                             g_rois, kMaxRoisPerWindow);

    // ROI audio now lives in the arena; the window can be refilled.
    xQueueSend(g_free_windows, &job.buffer, portMAX_DELAY);

    if (std::strcmp(current_session, job.session.id) != 0) {
      std::strcpy(current_session, job.session.id);
      next_sequence = 0;
    }

    g_stats.rois_detected += result.roi_count;
    if (result.roi_count == 0) {
      continue;
    }

    if (upload::format_edge_metadata(metadata, sizeof(metadata), result) ==
        0) {
      std::strcpy(metadata, "{}");
    }

    const double window_offset_seconds =
        static_cast<double>(job.offset_samples) / SAMPLE_RATE_HZ;

    for (size_t i = 0; i < result.roi_count; ++i) {
      const dsp::ProcessedRoi& roi = g_rois[i];
      // Every detected ROI takes a sequence number, so ROIs dropped
      // for lack of queue space show up as gaps on the backend.
      const uint32_t sequence = next_sequence++;

      xSemaphoreTake(g_queue_mutex, portMAX_DELAY);
      QueuedRoi* entry = g_queue.reserve(roi.sample_count);
      xSemaphoreGive(g_queue_mutex);

      if (entry == nullptr) {
        ++g_stats.rois_dropped_full;
        continue;
      }

      // The reserved entry is invisible to the uploader until commit,
      // so it can be filled without holding the mutex.
      new_uuid(entry->client_upload_id);
      std::strcpy(entry->capture_session_id, job.session.id);
      entry->session_start_mono_us = job.session.start_mono_us;
      entry->snippet_sequence = sequence;
      entry->roi_start_seconds =
          window_offset_seconds + roi.region.start_time_seconds;
      entry->roi_end_seconds =
          window_offset_seconds + roi.region.end_time_seconds;
      std::strcpy(entry->metadata, metadata);
      for (size_t k = 0; k < roi.sample_count; ++k) {
        entry->pcm[k] = upload::to_pcm16(roi.audio[k]);
      }

      xSemaphoreTake(g_queue_mutex, portMAX_DELAY);
      g_queue.commit();
      xSemaphoreGive(g_queue_mutex);

      ++g_stats.rois_queued;
      xTaskNotifyGive(g_upload_task);
    }
  }
}

// ------------------------------------------------------------
// Upload task
// ------------------------------------------------------------

bool is_permanent_rejection(int status) {
  return status >= 400 && status < 500 && status != 408 && status != 429;
}

void upload_task(void*) {
  uint32_t backoff_ms = UPLOAD_RETRY_INITIAL_MS;

  // capture_started_at is derived once per session from the clock
  // and the session's monotonic start time, so every ROI and every
  // retry of a session sends the same value. Sessions leave the
  // queue in order, so caching the latest one is enough.
  char cached_session[upload::kUuidStringLength + 1] = "";
  char cached_started_at[upload::kIso8601Length + 1] = "";

  for (;;) {
    xSemaphoreTake(g_queue_mutex, portMAX_DELAY);
    QueuedRoi* entry = g_queue.front();
    const size_t depth = g_queue.size();
    xSemaphoreGive(g_queue_mutex);

    if (entry == nullptr) {
      ulTaskNotifyTake(pdTRUE, portMAX_DELAY);
      continue;
    }

    if (!uplink_prepare(g_transport)) {
      ++g_stats.upload_failures;
      Serial.printf("upload: transport not ready, retrying in %u s\r\n",
                    static_cast<unsigned>(backoff_ms / 1000));
      delay(backoff_ms);
      backoff_ms = backoff_ms * 2 > UPLOAD_RETRY_MAX_MS ? UPLOAD_RETRY_MAX_MS
                                                        : backoff_ms * 2;
      continue;
    }

    if (std::strcmp(cached_session, entry->capture_session_id) != 0) {
      const int64_t session_age_ms =
          (esp_timer_get_time() - entry->session_start_mono_us) / 1000;
      upload::format_iso8601_utc(util::now_unix_ms() - session_age_ms,
                                 cached_started_at);
      std::strcpy(cached_session, entry->capture_session_id);
    }

    const upload::RoiUploadFields fields{
        DEVICE_ID,
        entry->client_upload_id,
        entry->capture_session_id,
        entry->snippet_sequence,
        cached_started_at,
        static_cast<float>(entry->roi_start_seconds),
        static_cast<float>(entry->roi_end_seconds),
        EDGE_PROCESSING_VERSION,
        entry->metadata};
    const upload::RoiAudio audio{nullptr, entry->pcm, entry->sample_count,
                                 SAMPLE_RATE_HZ};

    ++entry->attempts;
    const uint32_t started = millis();
    const int status = uplink_send(g_transport, fields, audio);
    Serial.printf(
        "upload: session %.8s seq %u (%.2f s audio) attempt %u -> %d "
        "(%.1f s), %u queued\r\n",
        entry->capture_session_id,
        static_cast<unsigned>(entry->snippet_sequence),
        static_cast<double>(entry->sample_count) / SAMPLE_RATE_HZ,
        static_cast<unsigned>(entry->attempts), status,
        (millis() - started) / 1000.0, static_cast<unsigned>(depth));

    if (status == 200 || status == 201 || is_permanent_rejection(status)) {
      if (status == 200 || status == 201) {
        ++g_stats.uploads_ok;
      } else {
        ++g_stats.uploads_rejected;
      }
      xSemaphoreTake(g_queue_mutex, portMAX_DELAY);
      g_queue.pop();
      xSemaphoreGive(g_queue_mutex);
      backoff_ms = UPLOAD_RETRY_INITIAL_MS;
      continue;
    }

    ++g_stats.upload_failures;
    delay(backoff_ms);
    backoff_ms = backoff_ms * 2 > UPLOAD_RETRY_MAX_MS ? UPLOAD_RETRY_MAX_MS
                                                      : backoff_ms * 2;
  }
}

}  // namespace

// ------------------------------------------------------------
// Public API
// ------------------------------------------------------------

bool start_monitor(Transport transport) {
  g_transport = transport;

  g_windows[0] = psram_alloc<float>(kWindowSamples);
  g_windows[1] = psram_alloc<float>(kWindowSamples);

  g_frame_capacity = dsp::pipeline_frame_count(kWindowSamples);
  g_energy = psram_alloc<float>(g_frame_capacity);
  g_smoothed = psram_alloc<float>(g_frame_capacity);
  // detect_regions caps silently at the capacity; this is the most
  // regions any frame pattern can produce.
  g_region_capacity = g_frame_capacity / 2 + 1;
  g_regions = psram_alloc<dsp::RegionOfInterest>(g_region_capacity);
  g_arena = psram_alloc<float>(kWindowSamples);

  QueuedRoi* entries = psram_alloc<QueuedRoi>(UPLOAD_QUEUE_MAX_ENTRIES);
  const size_t pool_samples = UPLOAD_QUEUE_POOL_BYTES / sizeof(int16_t);
  int16_t* pool = psram_alloc<int16_t>(pool_samples);

  if (!g_windows[0] || !g_windows[1] || !g_energy || !g_smoothed ||
      !g_regions || !g_arena || !entries || !pool) {
    Serial.print("monitor: PSRAM allocation failed\r\n");
    return false;
  }
  g_queue.init(entries, UPLOAD_QUEUE_MAX_ENTRIES, pool, pool_samples);

  g_queue_mutex = xSemaphoreCreateMutex();
  g_free_windows = xQueueCreate(2, sizeof(int));
  g_full_windows = xQueueCreate(2, sizeof(WindowJob));
  if (!g_queue_mutex || !g_free_windows || !g_full_windows) {
    Serial.print("monitor: could not create RTOS objects\r\n");
    return false;
  }
  for (int i = 0; i < 2; ++i) {
    xQueueSend(g_free_windows, &i, 0);
  }

  if (!audio::begin()) {
    Serial.print("monitor: I2S driver install failed\r\n");
    return false;
  }

  // Uploader first: the process task notifies it.
  xTaskCreatePinnedToCore(upload_task, "upload", 12288, nullptr, 3,
                          &g_upload_task, 0);
  xTaskCreatePinnedToCore(process_task, "process", 8192, nullptr, 5,
                          nullptr, 1);
  xTaskCreatePinnedToCore(capture_task, "capture", 4096, nullptr,
                          configMAX_PRIORITIES - 2, nullptr, 1);
  return true;
}

MonitorStats monitor_stats() {
  MonitorStats stats = g_stats;
  if (g_queue_mutex != nullptr) {
    xSemaphoreTake(g_queue_mutex, portMAX_DELAY);
    stats.queue_depth = g_queue.size();
    stats.queue_used_bytes = g_queue.used_samples() * sizeof(int16_t);
    xSemaphoreGive(g_queue_mutex);
  }
  return stats;
}

}  // namespace app
