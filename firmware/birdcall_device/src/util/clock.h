#pragma once

#include <cstdint>

// Wall-clock time for capture timestamps. Set from the network
// (A7670 NTP) in the field, or by the serial bridge on the bench.

namespace util {

void set_clock_unix_ms(int64_t unix_ms);

// True once set_clock_unix_ms() has been called since boot.
bool clock_is_set();

// Current time in Unix milliseconds (only meaningful once set).
int64_t now_unix_ms();

// Days since 1970-01-01 for a proleptic Gregorian date.
int64_t days_from_civil(int year, int month, int day);

}  // namespace util
