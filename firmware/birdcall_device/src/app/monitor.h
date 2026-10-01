#pragma once

#include <cstddef>
#include <cstdint>

#include "app/uplink.h"

// Continuous field operation: three FreeRTOS tasks connected by
// queues, so listening never pauses for processing or uploads.
//
//   capture  (core 1, highest priority)
//       reads the mic into back-to-back CAPTURE_WINDOW_SECONDS windows
//       (two PSRAM buffers, ping-pong); tracks capture sessions
//          |  full window
//          v
//   process  (core 1)
//       dsp::process_capture() per window; each ROI is converted to
//       PCM16 and queued with its session-relative times
//          |  RoiQueue (PSRAM ring)
//          v
//   upload   (core 0)
//       sends the oldest ROI; on success removes it, on network
//       failure keeps it and retries with back-off (same
//       client_upload_id and identical bytes, so the backend
//       recognises a repeat)

namespace app {

struct MonitorStats {
  uint32_t windows_captured;
  uint32_t windows_lost;  // dropped because processing fell behind or
                          // audio overflowed
  uint32_t sessions_started;
  uint32_t rois_detected;
  uint32_t rois_queued;
  uint32_t rois_dropped_full;  // queue full
  uint32_t uploads_ok;
  uint32_t uploads_rejected;   // 4xx: dropped, would never succeed
  uint32_t upload_failures;    // network/transport failures (retried)
  size_t queue_depth;
  size_t queue_used_bytes;
};

// Allocates buffers, starts the mic and the three tasks. Returns
// false if memory or the mic could not be set up.
bool start_monitor(Transport transport);

MonitorStats monitor_stats();

}  // namespace app
