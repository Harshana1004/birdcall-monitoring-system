#pragma once

#include <Arduino.h>

#include <cstddef>
#include <cstdint>

#include "upload/roi_upload.h"

// SIMCom A7670 (tested: A7670C-LNNV, firmware V11.0.01) over UART,
// using the module's own TCP/IP stack (AT+NETOPEN / AT+CIPOPEN).
//
// HTTP requests are written by hand over a raw TCP socket rather than
// through AT+HTTP*, so the multipart body can be streamed in chunks
// with no size limit and is byte-for-byte what the serial bridge
// sends. Received data uses manual mode (AT+CIPRXGET=1) so reads
// are length-prefixed and never interleave with command responses.

namespace modem {

class A7670 {
 public:
  // `log` receives every AT command and response line when non-null.
  A7670(HardwareSerial& port, Print* log);

  // Sends AT until the module answers OK, then configures it
  // (echo off, verbose errors). Returns false if it never answers.
  bool probe(uint32_t timeout_ms);

  // Waits for SIM ready and packet-domain registration (home or
  // roaming). Logs signal quality.
  bool wait_for_network(uint32_t timeout_ms);

  // Opens the module's data connection (PDP context 1) in manual
  // receive mode, restarting it if it was already open.
  bool open_data();

  // Syncs the module clock with NTP and returns UTC time. Returns
  // false if NTP or AT+CCLK? fails.
  bool sync_time(int64_t* unix_ms_out);

  // One HTTP/1.1 GET over TCP (connectivity check). Returns the HTTP
  // status code, or a negative value on transport failure.
  int http_get(const char* host, uint16_t port, const char* path);

  // POSTs one ROI as multipart/form-data (see upload/roi_upload.h),
  // streaming the body. Returns the HTTP status code (201 created,
  // 200 duplicate retry), or a negative value on transport failure.
  int post_roi(const char* host, uint16_t port, const char* path,
               const upload::RoiUploadFields& fields,
               const upload::RoiAudio& audio);

  // Bytes of socket data (headers + body) sent by the last request.
  size_t last_bytes_sent() const { return bytes_sent_; }

  // Used by the streaming sink; sends `length` bytes on socket 0.
  bool tcp_send(const uint8_t* data, size_t length);

 private:
  bool command(const char* cmd, uint32_t timeout_ms,
               const char* capture_prefix = nullptr, char* capture = nullptr,
               size_t capture_capacity = 0);
  bool read_line(char* out, size_t capacity, uint32_t timeout_ms);
  bool wait_for_prefix(const char* prefix, uint32_t timeout_ms, char* line,
                       size_t capacity);
  bool read_exact(uint8_t* out, size_t length, uint32_t timeout_ms);
  bool wait_for_prompt(uint32_t timeout_ms);
  void drain_input();
  void log_line(const char* direction, const char* text);

  bool tcp_open(const char* host, uint16_t port);
  void tcp_close();
  bool send_request_head(const char* method, const char* host,
                         uint16_t port, const char* path,
                         const char* content_type, size_t content_length);
  int read_http_status(uint32_t timeout_ms);

  HardwareSerial& port_;
  Print* log_;
  size_t bytes_sent_ = 0;
  // Set when the module reports "+IPCLOSE: 0,..." (server closed the
  // socket), so tcp_close() does not try to close it again.
  bool remote_closed_ = false;
};

}  // namespace modem
