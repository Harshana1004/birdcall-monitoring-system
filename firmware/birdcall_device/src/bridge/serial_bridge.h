#pragma once

#include <cstddef>
#include <cstdint>

#include "upload/roi_upload.h"

// Development transport used until the A7670 modem is fitted:
// tools/serial_bridge.py on the PC relays uploads to the backend
// and supplies wall-clock time.
//
// Protocol (text lines over the USB serial port):
//   PC -> device   "t<unix_ms>"              set the clock
//   device -> PC   "TIME_REQUEST"            ask for the clock
//   device -> PC   "UPLOAD_BEGIN <seq> <boundary> <content_length>"
//                  base64 body lines (76 chars)
//                  "UPLOAD_END"
//   PC -> device   "UPLOAD_RESULT <http_status>"  (0 = transport error)
//
// The device sends exactly the bytes it will later hand to the
// modem, so the bridge exercises the real request body.

namespace bridge {

// Streams bytes to Serial as base64, 76 chars per line.
class Base64SerialSink : public upload::ByteSink {
 public:
  void write(const uint8_t* data, size_t length) override;
  // Emits any buffered bytes (with '=' padding). Call once at the end.
  void finish();

 private:
  void flush_line();

  uint8_t pending_[57];  // 57 bytes -> one 76-char line
  size_t filled_ = 0;
};

// Reads one '\n'-terminated line from Serial into `out` (without the
// line ending). Returns false on timeout.
bool read_line(char* out, size_t capacity, uint32_t timeout_ms);

// Handles a "t<unix_ms>" line: sets the system clock (util/clock.h).
// Returns false if the line is not a valid time command.
bool apply_time_command(const char* line);

// Asks the bridge for the time and waits up to `timeout_ms`.
bool request_time(uint32_t timeout_ms);

// Sends one ROI upload through the bridge and waits for the backend's
// HTTP status. Returns the status (201 created, 200 duplicate retry),
// or 0 if the bridge did not answer in time.
int send_upload(const upload::RoiUploadFields& fields, const float* audio,
                size_t sample_count, uint32_t sample_rate,
                uint32_t response_timeout_ms);

}  // namespace bridge
