#include "bridge/serial_bridge.h"

#include <Arduino.h>

#include <cstdlib>
#include <cstring>

#include "util/clock.h"

namespace bridge {

namespace {

const char kAlphabet[] =
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

}  // namespace

void Base64SerialSink::write(const uint8_t* data, size_t length) {
  for (size_t i = 0; i < length; ++i) {
    pending_[filled_++] = data[i];
    if (filled_ == sizeof(pending_)) {
      flush_line();
    }
  }
}

void Base64SerialSink::finish() {
  if (filled_ > 0) {
    flush_line();
  }
}

void Base64SerialSink::flush_line() {
  char line[77];
  size_t out = 0;
  for (size_t i = 0; i < filled_; i += 3) {
    const uint32_t b0 = pending_[i];
    const uint32_t b1 = i + 1 < filled_ ? pending_[i + 1] : 0;
    const uint32_t b2 = i + 2 < filled_ ? pending_[i + 2] : 0;
    const uint32_t v = (b0 << 16) | (b1 << 8) | b2;
    line[out++] = kAlphabet[(v >> 18) & 63];
    line[out++] = kAlphabet[(v >> 12) & 63];
    line[out++] = i + 1 < filled_ ? kAlphabet[(v >> 6) & 63] : '=';
    line[out++] = i + 2 < filled_ ? kAlphabet[v & 63] : '=';
  }
  line[out] = '\0';
  Serial.println(line);
  filled_ = 0;
}

bool read_line(char* out, size_t capacity, uint32_t timeout_ms) {
  const uint32_t started = millis();
  size_t length = 0;

  while (millis() - started < timeout_ms) {
    while (Serial.available() > 0) {
      const char c = static_cast<char>(Serial.read());
      if (c == '\r') {
        continue;
      }
      if (c == '\n') {
        out[length] = '\0';
        return true;
      }
      if (length + 1 < capacity) {
        out[length++] = c;
      }
    }
    delay(1);
  }

  out[length] = '\0';
  return false;
}

bool apply_time_command(const char* line) {
  if (line[0] != 't' || line[1] == '\0') {
    return false;
  }

  char* end = nullptr;
  const long long unix_ms = std::strtoll(line + 1, &end, 10);
  if (end == line + 1 || *end != '\0' || unix_ms <= 0) {
    return false;
  }

  util::set_clock_unix_ms(unix_ms);
  return true;
}

bool request_time(uint32_t timeout_ms) {
  Serial.println("TIME_REQUEST");

  const uint32_t started = millis();
  char line[40];
  while (millis() - started < timeout_ms) {
    if (read_line(line, sizeof(line), timeout_ms - (millis() - started)) &&
        apply_time_command(line)) {
      return true;
    }
  }
  return false;
}

int send_upload(const upload::RoiUploadFields& fields, const float* audio,
                size_t sample_count, uint32_t sample_rate,
                uint32_t response_timeout_ms) {
  upload::CountingSink counter;
  upload::write_roi_upload_body(fields, audio, sample_count, sample_rate,
                                counter);

  char boundary[upload::kBoundaryMaxLength + 1];
  upload::format_boundary(fields, boundary);

  // Drop anything typed/sent before the upload so the reply we read
  // is the bridge's answer to this body.
  while (Serial.available() > 0) {
    Serial.read();
  }

  Serial.printf("UPLOAD_BEGIN %u %s %u\n",
                static_cast<unsigned>(fields.snippet_sequence), boundary,
                static_cast<unsigned>(counter.total));
  Base64SerialSink sink;
  upload::write_roi_upload_body(fields, audio, sample_count, sample_rate,
                                sink);
  sink.finish();
  Serial.println("UPLOAD_END");

  const uint32_t started = millis();
  char line[64];
  while (millis() - started < response_timeout_ms) {
    if (!read_line(line, sizeof(line),
                   response_timeout_ms - (millis() - started))) {
      break;
    }
    if (std::strncmp(line, "UPLOAD_RESULT ", 14) == 0) {
      return std::atoi(line + 14);
    }
    apply_time_command(line);  // the bridge may resend the clock
  }
  return 0;
}

}  // namespace bridge
