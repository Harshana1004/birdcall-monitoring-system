#pragma once

#include <cstddef>
#include <cstdint>

namespace audio {

// I2S capture from the INMP441 at SAMPLE_RATE_HZ, mono.
//
// The INMP441 sends 24-bit samples left-justified in 32-bit I2S
// slots; read() converts them to float in [-1, 1) and applies the
// MIC_DC_BLOCK_CUTOFF_HZ DC blocker.

// Installs the I2S driver and discards the mic's startup
// transient. Returns false if the driver could not be installed.
bool begin();

// Blocks until `count` samples have been written to `out`.
// Returns the number of samples read (less than `count` only on
// a driver error).
size_t read(float* out, size_t count);

// Diagnostics: reads unconverted 32-bit I2S slots (no shift, no DC
// blocker). Blocks until `count` slots have been read.
size_t read_raw_slots(int32_t* out, size_t count);

void end();

}  // namespace audio
