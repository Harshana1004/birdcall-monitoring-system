#include "upload/uuid.h"

namespace upload {

void format_uuid_v4(const uint8_t random_bytes[16], char* out) {
  static const char kHex[] = "0123456789abcdef";

  uint8_t b[16];
  for (int i = 0; i < 16; ++i) {
    b[i] = random_bytes[i];
  }
  b[6] = static_cast<uint8_t>((b[6] & 0x0F) | 0x40);  // version 4
  b[8] = static_cast<uint8_t>((b[8] & 0x3F) | 0x80);  // RFC 4122 variant

  int pos = 0;
  for (int i = 0; i < 16; ++i) {
    if (i == 4 || i == 6 || i == 8 || i == 10) {
      out[pos++] = '-';
    }
    out[pos++] = kHex[b[i] >> 4];
    out[pos++] = kHex[b[i] & 0x0F];
  }
  out[pos] = '\0';
}

}  // namespace upload
