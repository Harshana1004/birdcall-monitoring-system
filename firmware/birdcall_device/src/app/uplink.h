#pragma once

#include "modem/a7670.h"
#include "upload/roi_upload.h"

// The path ROI uploads take to the backend: the A7670 over 4G in the
// field, or the USB serial bridge (tools/serial_bridge.py) on the
// bench. Owns the single modem instance.

namespace app {

enum class Transport { kSerialBridge, kModem };

modem::A7670& modem_link();

// Makes `transport` ready to send and ensures the clock is set:
//   modem  -- answers AT, registered, data connection open, NTP time
//   bridge -- clock received from the bridge (asks for it if needed)
// Cheap when already ready. Returns false if not ready.
bool uplink_prepare(Transport transport);

// Sends one ROI. Returns the HTTP status (201 created, 200 duplicate
// retry), 0 if the bridge did not answer, or a negative value on a
// modem transport failure (the next uplink_prepare() then re-checks
// the modem from scratch).
int uplink_send(Transport transport, const upload::RoiUploadFields& fields,
                const upload::RoiAudio& audio);

}  // namespace app
