#include "app/uplink.h"

#include <Arduino.h>

#include <cstring>

#include "bridge/serial_bridge.h"
#include "config.h"
#include "upload/edge_metadata.h"
#include "util/clock.h"

#if __has_include("secrets.h")
#include "secrets.h"
#else
#error "include/secrets.h is missing: copy include/secrets.example.h to include/secrets.h and set DEVICE_API_KEY"
#endif

namespace app {

namespace {

constexpr uint32_t kBridgeResponseTimeoutMs = 30000;

// Logs every AT exchange to the USB serial port.
modem::A7670 g_modem(Serial1, &Serial);
bool g_modem_ready = false;

bool prepare_modem() {
  if (g_modem_ready) {
    return true;
  }
  if (!g_modem.probe(10000)) {
    Serial.print("modem: no answer to AT -- check wiring and power\r\n");
    return false;
  }
  if (!g_modem.wait_for_network(60000)) {
    Serial.print("modem: not registered on the network\r\n");
    return false;
  }
  if (!g_modem.open_data()) {
    Serial.print("modem: could not open the data connection\r\n");
    return false;
  }
  if (!util::clock_is_set()) {
    int64_t unix_ms = 0;
    if (!g_modem.sync_time(&unix_ms)) {
      Serial.print("modem: NTP time sync failed\r\n");
      return false;
    }
    util::set_clock_unix_ms(unix_ms);
    char iso[upload::kIso8601Length + 1];
    upload::format_iso8601_utc(unix_ms, iso);
    Serial.printf("modem: clock set to %s\r\n", iso);
  }
  g_modem_ready = true;
  return true;
}

}  // namespace

modem::A7670& modem_link() {
  return g_modem;
}

bool uplink_prepare(Transport transport) {
  if (transport == Transport::kModem) {
    if (std::strncmp(DEVICE_API_KEY, "REPLACE_", 8) == 0) {
      Serial.print("upload: DEVICE_API_KEY in include/secrets.h is still "
                   "the placeholder -- the server will reject uploads\r\n");
    }
    return prepare_modem();
  }
  return util::clock_is_set() || bridge::request_time(3000);
}

int uplink_send(Transport transport, const upload::RoiUploadFields& fields,
                const upload::RoiAudio& audio) {
  if (transport == Transport::kSerialBridge) {
    return bridge::send_upload(fields, audio, kBridgeResponseTimeoutMs);
  }
  const int status =
      g_modem.post_roi(BACKEND_HOST, BACKEND_PORT, BACKEND_UPLOAD_PATH,
                       DEVICE_API_KEY, fields, audio);
  if (status < 0) {
    g_modem_ready = false;  // re-check registration/data next time
  }
  if (status == 401) {
    Serial.print("upload: 401 -- DEVICE_API_KEY in include/secrets.h does "
                 "not match the server's\r\n");
  }
  return status;
}

}  // namespace app
