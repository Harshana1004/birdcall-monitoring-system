#pragma once

#include <cstddef>
#include <cstdint>

#include "upload/uuid.h"

// FIFO of ROIs waiting to be uploaded. PCM16 audio lives in one
// caller-supplied pool used as a ring: since entries are always
// freed oldest-first, each new ROI goes either after the newest one
// or, if the end of the pool is too short, wraps to the start --
// no fragmentation, no per-ROI heap allocation.
//
// Not thread-safe: the caller serialises access (app/monitor.cpp
// holds a mutex around each call). One producer may hold a single
// reserved entry while the consumer works on the front entry.

namespace app {

constexpr size_t kQueuedMetadataCapacity = 640;

struct QueuedRoi {
  char client_upload_id[upload::kUuidStringLength + 1];
  char capture_session_id[upload::kUuidStringLength + 1];
  int64_t session_start_mono_us;  // esp_timer time of session's first sample
  uint32_t snippet_sequence;
  double roi_start_seconds;  // relative to the session start
  double roi_end_seconds;
  char metadata[kQueuedMetadataCapacity];  // edge_processing_metadata JSON
  uint32_t attempts;

  int16_t* pcm;  // points into the pool
  size_t sample_count;
  size_t offset;  // position of `pcm` in the pool (samples)
};

class RoiQueue {
 public:
  RoiQueue() = default;

  // `entries` must hold `max_entries` items; `pool` holds
  // `pool_samples` int16 samples.
  void init(QueuedRoi* entries, size_t max_entries, int16_t* pool,
            size_t pool_samples);

  // Producer: claims space for `sample_count` samples. Returns the
  // entry to fill (its `pcm`/`sample_count` already set), or nullptr
  // if there is no room. Invisible to the consumer until commit().
  QueuedRoi* reserve(size_t sample_count);
  void commit();
  void cancel();

  // Consumer: oldest committed entry, or nullptr if empty. Stays
  // valid until pop().
  QueuedRoi* front();
  void pop();

  size_t size() const { return count_; }
  size_t capacity() const { return max_entries_; }
  size_t pool_samples() const { return pool_samples_; }
  // Samples between the oldest entry and the allocation point,
  // including any skipped tail at a wrap (approximate fill level).
  size_t used_samples() const;

 private:
  QueuedRoi* entries_ = nullptr;
  size_t max_entries_ = 0;
  int16_t* pool_ = nullptr;
  size_t pool_samples_ = 0;

  size_t first_ = 0;  // index of the oldest committed entry
  size_t count_ = 0;  // committed entries
  size_t head_ = 0;   // next free pool position (samples)

  bool pending_ = false;
  size_t pending_saved_head_ = 0;
};

}  // namespace app
