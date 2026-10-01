#include "modem/a7670.h"

#include <cstdio>
#include <cstring>

#include "util/clock.h"

namespace modem {

namespace {

constexpr int kLink = 0;                 // socket link number used
constexpr size_t kSendChunkBytes = 1024;  // per AT+CIPSEND
constexpr uint32_t kSendTimeoutMs = 15000;

// Negative return codes for transport failures.
constexpr int kErrConnect = -1;
constexpr int kErrSend = -2;
constexpr int kErrNoResponse = -3;

bool starts_with(const char* s, const char* prefix) {
  return std::strncmp(s, prefix, std::strlen(prefix)) == 0;
}

bool is_error_line(const char* line) {
  return std::strcmp(line, "ERROR") == 0 || starts_with(line, "+CME ERROR") ||
         starts_with(line, "+IP ERROR") || starts_with(line, "+CIPERROR");
}

// Streams the request body to the modem in kSendChunkBytes pieces.
class ModemSink : public upload::ByteSink {
 public:
  explicit ModemSink(A7670& modem) : modem_(modem) {}

  void write(const uint8_t* data, size_t length) override {
    for (size_t i = 0; i < length; ++i) {
      buffer_[filled_++] = data[i];
      if (filled_ == sizeof(buffer_)) {
        flush();
      }
    }
  }

  // Sends any buffered bytes; returns false if any send failed.
  bool finish() {
    if (filled_ > 0) {
      flush();
    }
    return ok_;
  }

 private:
  void flush() {
    if (ok_) {
      ok_ = modem_.tcp_send(buffer_, filled_);
    }
    filled_ = 0;
  }

  A7670& modem_;
  uint8_t buffer_[kSendChunkBytes];
  size_t filled_ = 0;
  bool ok_ = true;
};

}  // namespace

A7670::A7670(HardwareSerial& port, Print* log) : port_(port), log_(log) {}

// ------------------------------------------------------------
// Low-level I/O
// ------------------------------------------------------------

void A7670::log_line(const char* direction, const char* text) {
  if (log_ != nullptr) {
    log_->printf("  %s %s\n", direction, text);
  }
}

void A7670::drain_input() {
  char line[128];
  while (port_.available() > 0) {
    if (read_line(line, sizeof(line), 50) && line[0] != '\0') {
      // read_line already logged it (stray URC).
    }
  }
}

bool A7670::read_line(char* out, size_t capacity, uint32_t timeout_ms) {
  const uint32_t started = millis();
  size_t length = 0;

  while (millis() - started < timeout_ms) {
    if (port_.available() == 0) {
      delay(1);
      continue;
    }
    const char c = static_cast<char>(port_.read());
    if (c == '\r') {
      continue;
    }
    if (c == '\n') {
      if (length == 0) {
        continue;  // skip blank lines
      }
      out[length] = '\0';
      log_line("<", out);
      if (starts_with(out, "+IPCLOSE: 0,")) {
        remote_closed_ = true;
      }
      return true;
    }
    if (length + 1 < capacity) {
      out[length++] = c;
    }
  }

  out[length] = '\0';
  return false;
}

bool A7670::wait_for_prefix(const char* prefix, uint32_t timeout_ms,
                            char* line, size_t capacity) {
  const uint32_t started = millis();
  while (millis() - started < timeout_ms) {
    if (!read_line(line, capacity, timeout_ms - (millis() - started))) {
      return false;
    }
    if (starts_with(line, prefix)) {
      return true;
    }
    if (is_error_line(line)) {
      return false;
    }
  }
  return false;
}

bool A7670::command(const char* cmd, uint32_t timeout_ms,
                    const char* capture_prefix, char* capture,
                    size_t capture_capacity) {
  drain_input();
  log_line(">", cmd);
  port_.print(cmd);
  port_.print('\r');

  if (capture != nullptr && capture_capacity > 0) {
    capture[0] = '\0';
  }

  char line[160];
  const uint32_t started = millis();
  while (millis() - started < timeout_ms) {
    if (!read_line(line, sizeof(line), timeout_ms - (millis() - started))) {
      break;
    }
    if (std::strcmp(line, "OK") == 0) {
      return true;
    }
    if (is_error_line(line)) {
      return false;
    }
    if (capture_prefix != nullptr && capture != nullptr &&
        starts_with(line, capture_prefix)) {
      std::snprintf(capture, capture_capacity, "%s", line);
    }
  }
  log_line("!", "timeout");
  return false;
}

bool A7670::read_exact(uint8_t* out, size_t length, uint32_t timeout_ms) {
  const uint32_t started = millis();
  size_t got = 0;
  while (got < length) {
    if (millis() - started >= timeout_ms) {
      return false;
    }
    if (port_.available() > 0) {
      out[got++] = static_cast<uint8_t>(port_.read());
    } else {
      delay(1);
    }
  }
  return true;
}

bool A7670::wait_for_prompt(uint32_t timeout_ms) {
  const uint32_t started = millis();
  char line[64];
  size_t length = 0;

  while (millis() - started < timeout_ms) {
    if (port_.available() == 0) {
      delay(1);
      continue;
    }
    const char c = static_cast<char>(port_.read());
    if (c == '>' && length == 0) {
      return true;
    }
    if (c == '\r') {
      continue;
    }
    if (c == '\n') {
      if (length > 0) {
        line[length] = '\0';
        log_line("<", line);
        if (is_error_line(line)) {
          return false;
        }
        length = 0;
      }
      continue;
    }
    if (length + 1 < sizeof(line)) {
      line[length++] = c;
    }
  }
  return false;
}

// ------------------------------------------------------------
// Module and network setup
// ------------------------------------------------------------

bool A7670::probe(uint32_t timeout_ms) {
  const uint32_t started = millis();
  bool answered = false;
  while (!answered && millis() - started < timeout_ms) {
    answered = command("AT", 1000);
  }
  if (!answered) {
    return false;
  }
  command("ATE0", 1000);       // no command echo: simpler parsing
  command("AT+CMEE=2", 1000);  // verbose error text
  return true;
}

bool A7670::wait_for_network(uint32_t timeout_ms) {
  char line[96];
  const uint32_t started = millis();

  bool sim_ready = false;
  while (!sim_ready && millis() - started < timeout_ms) {
    sim_ready = command("AT+CPIN?", 5000, "+CPIN:", line, sizeof(line)) &&
                std::strstr(line, "READY") != nullptr;
    if (!sim_ready) {
      delay(1000);
    }
  }
  if (!sim_ready) {
    return false;
  }

  while (millis() - started < timeout_ms) {
    int n = 0;
    int stat = 0;
    if (command("AT+CGREG?", 5000, "+CGREG:", line, sizeof(line)) &&
        std::sscanf(line, "+CGREG: %d,%d", &n, &stat) == 2 &&
        (stat == 1 || stat == 5)) {
      command("AT+CSQ", 2000);
      command("AT+CPSI?", 2000);
      return true;
    }
    delay(2000);
  }
  return false;
}

bool A7670::open_data() {
  char line[96];

  // AT+CIPRXGET must be set while the network is closed.
  if (command("AT+NETOPEN?", 5000, "+NETOPEN:", line, sizeof(line)) &&
      std::strcmp(line, "+NETOPEN: 1") == 0) {
    if (command("AT+NETCLOSE", 10000)) {
      wait_for_prefix("+NETCLOSE:", 10000, line, sizeof(line));
    }
  }

  if (!command("AT+CIPRXGET=1", 2000)) {
    return false;
  }

  if (!command("AT+NETOPEN", 5000)) {
    return false;
  }
  int err = -1;
  if (!wait_for_prefix("+NETOPEN:", 30000, line, sizeof(line)) ||
      std::sscanf(line, "+NETOPEN: %d", &err) != 1 || err != 0) {
    return false;
  }

  command("AT+IPADDR", 5000);
  return true;
}

bool A7670::sync_time(int64_t* unix_ms_out) {
  char line[96];

  // Timezone argument 0: the module clock is set to UTC.
  if (!command("AT+CNTP=\"pool.ntp.org\",0", 5000) ||
      !command("AT+CNTP", 5000)) {
    return false;
  }
  int err = -1;
  if (!wait_for_prefix("+CNTP:", 60000, line, sizeof(line)) ||
      std::sscanf(line, "+CNTP: %d", &err) != 1 || err != 0) {
    return false;
  }

  // +CCLK: "yy/MM/dd,hh:mm:ss+zz" with zz in quarter hours.
  if (!command("AT+CCLK?", 2000, "+CCLK:", line, sizeof(line))) {
    return false;
  }
  int yy, mo, dd, hh, mi, ss, tz;
  char sign;
  if (std::sscanf(line, "+CCLK: \"%d/%d/%d,%d:%d:%d%c%d\"", &yy, &mo, &dd,
                  &hh, &mi, &ss, &sign, &tz) != 8) {
    return false;
  }
  const int tz_minutes = (sign == '-' ? -tz : tz) * 15;
  const int64_t local_seconds =
      util::days_from_civil(2000 + yy, mo, dd) * 86400 + hh * 3600 +
      mi * 60 + ss;
  *unix_ms_out = (local_seconds - tz_minutes * 60) * 1000;
  return true;
}

// ------------------------------------------------------------
// TCP
// ------------------------------------------------------------

bool A7670::tcp_open(const char* host, uint16_t port) {
  char cmd[160];
  std::snprintf(cmd, sizeof(cmd), "AT+CIPOPEN=%d,\"TCP\",\"%s\",%u", kLink,
                host, static_cast<unsigned>(port));

  for (int attempt = 0; attempt < 2; ++attempt) {
    char line[64];
    int link = -1;
    int err = -1;
    if (command(cmd, 5000) &&
        wait_for_prefix("+CIPOPEN:", 30000, line, sizeof(line)) &&
        std::sscanf(line, "+CIPOPEN: %d,%d", &link, &err) == 2 && err == 0) {
      bytes_sent_ = 0;
      remote_closed_ = false;
      return true;
    }
    tcp_close();  // link may be stuck open from an earlier request
  }
  return false;
}

void A7670::tcp_close() {
  if (remote_closed_) {
    remote_closed_ = false;
    return;  // already closed by the server
  }
  char line[64];
  if (command("AT+CIPCLOSE=0", 5000)) {
    wait_for_prefix("+CIPCLOSE:", 5000, line, sizeof(line));
  }
}

bool A7670::tcp_send(const uint8_t* data, size_t length) {
  while (length > 0) {
    const size_t n = length < kSendChunkBytes ? length : kSendChunkBytes;

    char cmd[40];
    std::snprintf(cmd, sizeof(cmd), "AT+CIPSEND=%d,%u", kLink,
                  static_cast<unsigned>(n));
    drain_input();
    port_.print(cmd);
    port_.print('\r');
    if (!wait_for_prompt(5000)) {
      log_line("!", "no send prompt");
      return false;
    }
    port_.write(data, n);

    // Wait for "+CIPSEND: <link>,<requested>,<confirmed>".
    char line[64];
    unsigned requested = 0;
    unsigned confirmed = 0;
    int link = -1;
    if (!wait_for_prefix("+CIPSEND:", kSendTimeoutMs, line, sizeof(line)) ||
        std::sscanf(line, "+CIPSEND: %d,%u,%u", &link, &requested,
                    &confirmed) != 3 ||
        confirmed != n) {
      log_line("!", "send not confirmed");
      return false;
    }

    bytes_sent_ += n;
    data += n;
    length -= n;
  }
  return true;
}

bool A7670::send_request_head(const char* method, const char* host,
                              uint16_t port, const char* path,
                              const char* content_type,
                              size_t content_length,
                              const char* device_key) {
  char host_header[96];
  if (port == 80) {
    std::snprintf(host_header, sizeof(host_header), "%s", host);
  } else {
    std::snprintf(host_header, sizeof(host_header), "%s:%u", host,
                  static_cast<unsigned>(port));
  }

  char key_header[160] = "";
  if (device_key != nullptr && device_key[0] != '\0') {
    std::snprintf(key_header, sizeof(key_header), "X-Device-Key: %s\r\n",
                  device_key);
  }

  char head[512];
  int n;
  if (content_type != nullptr) {
    n = std::snprintf(head, sizeof(head),
                      "%s %s HTTP/1.1\r\nHost: %s\r\nUser-Agent: "
                      "birdcall-device\r\n%sContent-Type: %s\r\n"
                      "Content-Length: %u\r\nConnection: close\r\n\r\n",
                      method, path, host_header, key_header, content_type,
                      static_cast<unsigned>(content_length));
  } else {
    n = std::snprintf(head, sizeof(head),
                      "%s %s HTTP/1.1\r\nHost: %s\r\nUser-Agent: "
                      "birdcall-device\r\n%sConnection: close\r\n\r\n",
                      method, path, host_header, key_header);
  }
  if (n <= 0 || static_cast<size_t>(n) >= sizeof(head)) {
    return false;
  }
  return tcp_send(reinterpret_cast<const uint8_t*>(head),
                  static_cast<size_t>(n));
}

int A7670::read_http_status(uint32_t timeout_ms) {
  // Only the status line matters; keep the first bytes of the reply.
  char reply[256];
  size_t filled = 0;
  const uint32_t started = millis();

  while (millis() - started < timeout_ms) {
    drain_input();
    const char* cmd = "AT+CIPRXGET=2,0,128";
    log_line(">", cmd);
    port_.print(cmd);
    port_.print('\r');

    // "+CIPRXGET: 2,<link>,<read_len>,<rest_len>" then read_len raw
    // bytes, then OK. With no data yet the module answers ERROR.
    char line[96];
    bool got_data = false;
    const uint32_t cmd_started = millis();
    while (millis() - cmd_started < 3000 &&
           read_line(line, sizeof(line), 3000 - (millis() - cmd_started))) {
      int link = -1;
      unsigned read_len = 0;
      unsigned rest_len = 0;
      if (std::sscanf(line, "+CIPRXGET: 2,%d,%u,%u", &link, &read_len,
                      &rest_len) == 3) {
        uint8_t chunk[128];
        if (read_len > sizeof(chunk) ||
            !read_exact(chunk, read_len, 2000)) {
          return kErrNoResponse;
        }
        const size_t room = sizeof(reply) - 1 - filled;
        const size_t take = read_len < room ? read_len : room;
        std::memcpy(reply + filled, chunk, take);
        filled += take;
        reply[filled] = '\0';
        got_data = read_len > 0;
        continue;
      }
      if (std::strcmp(line, "OK") == 0 || is_error_line(line)) {
        break;
      }
    }

    if (std::strstr(reply, "\r\n") != nullptr) {
      int status = 0;
      if (std::sscanf(reply, "HTTP/%*s %d", &status) == 1) {
        char status_line[64];
        std::snprintf(status_line, sizeof(status_line), "%.*s",
                      static_cast<int>(std::strcspn(reply, "\r")), reply);
        log_line("=", status_line);
        return status;
      }
      return kErrNoResponse;
    }

    if (!got_data) {
      delay(250);
    }
  }
  return kErrNoResponse;
}

// ------------------------------------------------------------
// HTTP
// ------------------------------------------------------------

int A7670::http_get(const char* host, uint16_t port, const char* path) {
  if (!tcp_open(host, port)) {
    return kErrConnect;
  }
  int status = kErrSend;
  if (send_request_head("GET", host, port, path, nullptr, 0, nullptr)) {
    status = read_http_status(30000);
  }
  tcp_close();
  return status;
}

int A7670::post_roi(const char* host, uint16_t port, const char* path,
                    const char* device_key,
                    const upload::RoiUploadFields& fields,
                    const upload::RoiAudio& audio) {
  upload::CountingSink counter;
  upload::write_roi_upload_body(fields, audio, counter);

  char boundary[upload::kBoundaryMaxLength + 1];
  upload::format_boundary(fields, boundary);
  char content_type[upload::kBoundaryMaxLength + 40];
  std::snprintf(content_type, sizeof(content_type),
                "multipart/form-data; boundary=%s", boundary);

  if (!tcp_open(host, port)) {
    return kErrConnect;
  }

  // Per-chunk AT traffic would flood the log; keep only the outcome.
  Print* saved_log = log_;
  int status = kErrSend;
  if (send_request_head("POST", host, port, path, content_type,
                        counter.total, device_key)) {
    log_ = nullptr;
    ModemSink sink(*this);
    upload::write_roi_upload_body(fields, audio, sink);
    const bool sent = sink.finish();
    log_ = saved_log;
    if (sent) {
      status = read_http_status(30000);
    } else {
      log_line("!", "body send failed");
    }
  }
  log_ = saved_log;

  tcp_close();
  return status;
}

}  // namespace modem
