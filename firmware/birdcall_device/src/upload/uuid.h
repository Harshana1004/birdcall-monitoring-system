#pragma once

#include <cstdint>

namespace upload {

constexpr int kUuidStringLength = 36;

// Formats 16 random bytes as a lowercase RFC 4122 version-4 UUID
// string (sets the version and variant bits). `out` must hold
// kUuidStringLength + 1 chars.
void format_uuid_v4(const uint8_t random_bytes[16], char* out);

}  // namespace upload
