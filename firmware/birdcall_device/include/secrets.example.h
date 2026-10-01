#pragma once

// Template for include/secrets.h, which is git-ignored. Copy this
// file to secrets.h and fill in the real values; never commit them.

// Must equal DEVICE_API_KEY in the server's backend/.env -- printed at
// the end of deploy/setup_server.sh. Sent as the X-Device-Key header
// with every ROI upload over 4G.
constexpr const char* DEVICE_API_KEY = "REPLACE_WITH_DEVICE_API_KEY";
