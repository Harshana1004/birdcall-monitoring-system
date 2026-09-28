#pragma once

#include <cstddef>
#include <cstdint>

#include "dsp/dsp_pipeline.h"

namespace upload {

// Formats the edge_processing_metadata JSON object for one capture:
// the pipeline parameters from config.h (so the backend can tell
// exactly how a snippet was produced) plus this capture's measured
// values. Returns the length written, or 0 if `capacity` is too
// small.
size_t format_edge_metadata(char* out, size_t capacity,
                            const dsp::PipelineResult& result);

// Formats Unix time in milliseconds as ISO 8601 UTC,
// e.g. "2026-09-24T10:15:30.123+00:00". `out` must hold
// kIso8601Length + 1 chars.
constexpr size_t kIso8601Length = 29;
void format_iso8601_utc(int64_t unix_ms, char* out);

}  // namespace upload
