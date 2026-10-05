#include "upload/edge_metadata.h"

#include <cmath>
#include <cstdio>

#include "config.h"

namespace upload {

size_t format_edge_metadata(char* out, size_t capacity,
                            const dsp::PipelineResult& result) {
  // Infinite when the capture was all zeros; JSON has no infinity.
  const float peak_threshold =
      std::isfinite(result.peak_threshold) ? result.peak_threshold : -1.0f;

  const int written = std::snprintf(
      out, capacity,
      "{"
      "\"firmware\":\"birdcall_device\","
      "\"microphone\":\"INMP441\","
      "\"sample_rate_hz\":%u,"
      "\"dc_block_cutoff_hz\":%.1f,"
      "\"highpass\":{\"type\":\"butterworth\",\"order\":%u,"
      "\"cutoff_hz\":%.1f,\"mode\":\"causal_sosfilt\","
      "\"applied_to\":\"detection_only\"},"
      "\"normalization\":{\"method\":\"peak\",\"input_peak\":%.6g,"
      "\"band_peak\":%.6g},"
      "\"energy\":{\"frame_seconds\":%.3f,\"hop_seconds\":%.3f,"
      "\"smoothing_window_frames\":%u,\"threshold_factor\":%.2f,"
      "\"threshold\":%.6g},"
      "\"peak_gate\":{\"min_peak_factor\":%.2f,\"min_peak_dbfs\":%.1f,"
      "\"threshold\":%.6g,\"rejected_regions\":%u},"
      "\"levels_dbfs\":{\"noise_floor\":%.1f,\"loudest\":%.1f},"
      "\"roi\":{\"min_duration_seconds\":%.2f,\"merge_gap_seconds\":%.2f,"
      "\"padding_seconds\":%.2f,\"birdnet_padding\":\"none\"},"
      "\"capture_seconds\":%.3f"
      "}",
      static_cast<unsigned>(SAMPLE_RATE_HZ), MIC_DC_BLOCK_CUTOFF_HZ,
      static_cast<unsigned>(HIGHPASS_FILTER_ORDER), HIGHPASS_CUTOFF_HZ,
      result.input_peak, result.band_peak, FRAME_DURATION_SECONDS,
      HOP_DURATION_SECONDS, static_cast<unsigned>(ENERGY_SMOOTHING_WINDOW),
      ROI_THRESHOLD_FACTOR, result.energy_threshold, ROI_MIN_PEAK_FACTOR,
      ROI_MIN_PEAK_DBFS, peak_threshold,
      static_cast<unsigned>(result.rejected_region_count),
      result.noise_floor_dbfs, result.loudest_dbfs, ROI_MIN_DURATION_SECONDS,
      ROI_MERGE_GAP_SECONDS, ROI_PADDING_SECONDS, result.duration_seconds);

  if (written < 0 || static_cast<size_t>(written) >= capacity) {
    return 0;
  }
  return static_cast<size_t>(written);
}

void format_iso8601_utc(int64_t unix_ms, char* out) {
  int64_t seconds = unix_ms / 1000;
  int millis = static_cast<int>(unix_ms % 1000);
  if (millis < 0) {
    millis += 1000;
    seconds -= 1;
  }

  int64_t days = seconds / 86400;
  int64_t day_seconds = seconds % 86400;
  if (day_seconds < 0) {
    day_seconds += 86400;
    days -= 1;
  }

  // Days since 1970-01-01 -> civil date (Howard Hinnant's algorithm).
  days += 719468;
  const int64_t era = (days >= 0 ? days : days - 146096) / 146097;
  const int64_t doe = days - era * 146097;
  const int64_t yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
  const int64_t doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
  const int64_t mp = (5 * doy + 2) / 153;
  const int day = static_cast<int>(doy - (153 * mp + 2) / 5 + 1);
  const int month = static_cast<int>(mp < 10 ? mp + 3 : mp - 9);
  const int year = static_cast<int>(yoe + era * 400 + (month <= 2 ? 1 : 0));

  std::snprintf(out, kIso8601Length + 1,
                "%04d-%02d-%02dT%02d:%02d:%02d.%03d+00:00", year, month, day,
                static_cast<int>(day_seconds / 3600),
                static_cast<int>(day_seconds % 3600 / 60),
                static_cast<int>(day_seconds % 60), millis);
}

}  // namespace upload
