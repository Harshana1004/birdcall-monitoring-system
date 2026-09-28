#include "util/clock.h"

#include <sys/time.h>

namespace util {

namespace {

bool g_clock_set = false;

}  // namespace

void set_clock_unix_ms(int64_t unix_ms) {
  timeval tv;
  tv.tv_sec = static_cast<time_t>(unix_ms / 1000);
  tv.tv_usec = static_cast<suseconds_t>((unix_ms % 1000) * 1000);
  settimeofday(&tv, nullptr);
  g_clock_set = true;
}

bool clock_is_set() {
  return g_clock_set;
}

int64_t now_unix_ms() {
  timeval tv;
  gettimeofday(&tv, nullptr);
  return static_cast<int64_t>(tv.tv_sec) * 1000 + tv.tv_usec / 1000;
}

int64_t days_from_civil(int year, int month, int day) {
  // Howard Hinnant's algorithm (inverse of the one used in
  // upload::format_iso8601_utc).
  year -= month <= 2 ? 1 : 0;
  const int64_t era = (year >= 0 ? year : year - 399) / 400;
  const int64_t yoe = year - era * 400;
  const int64_t doy = (153 * (month > 2 ? month - 3 : month + 9) + 2) / 5 + day - 1;
  const int64_t doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
  return era * 146097 + doe - 719468;
}

}  // namespace util
