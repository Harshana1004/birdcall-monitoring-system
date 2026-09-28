#pragma once

#include <cstddef>
#include <cstdint>

namespace upload {

// Receives the request body as it is produced, so it can be
// streamed straight to the modem (or counted) without holding the
// whole multipart body in memory.
class ByteSink {
 public:
  virtual ~ByteSink() = default;
  virtual void write(const uint8_t* data, size_t length) = 0;
};

class CountingSink : public ByteSink {
 public:
  void write(const uint8_t*, size_t length) override { total += length; }
  size_t total = 0;
};

// Form fields for POST /api/v1/recordings (see
// backend/src/api/recordings.py). All strings are NUL-terminated.
struct RoiUploadFields {
  const char* device_id;            // UUID of the registered Device
  const char* client_upload_id;     // UUID, unique per ROI, reused on retry
  const char* capture_session_id;   // UUID shared by one capture session
  uint32_t snippet_sequence;        // 0-based ROI index in the session
  const char* capture_started_at;   // ISO 8601 with offset
  float roi_start_seconds;          // relative to capture start
  float roi_end_seconds;
  const char* edge_processing_version;
  const char* edge_processing_metadata;  // JSON object
};

// Boundary used by write_roi_upload_body(); callers need it for
// the Content-Type header:
//   multipart/form-data; boundary=<boundary>
// Derived from client_upload_id, so it is stable across retries.
// `out` must hold kBoundaryMaxLength + 1 chars.
constexpr size_t kBoundaryMaxLength = 70;
void format_boundary(const RoiUploadFields& fields, char* out);

// Writes the complete multipart/form-data body -- all form fields
// plus `audio` as a mono PCM16 WAV named "<client_upload_id>.wav".
// Call once with a CountingSink to get Content-Length, then again
// with the real sink; the output is identical both times.
void write_roi_upload_body(const RoiUploadFields& fields, const float* audio,
                           size_t sample_count, uint32_t sample_rate,
                           ByteSink& sink);

}  // namespace upload
