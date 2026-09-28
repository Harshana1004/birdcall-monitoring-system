#include "upload/roi_upload.h"

#include <cstdio>
#include <cstring>

#include "upload/wav_writer.h"

namespace upload {

namespace {

void write_str(ByteSink& sink, const char* s) {
  sink.write(reinterpret_cast<const uint8_t*>(s), std::strlen(s));
}

void write_part_header(ByteSink& sink, const char* boundary,
                       const char* name) {
  write_str(sink, "--");
  write_str(sink, boundary);
  write_str(sink, "\r\nContent-Disposition: form-data; name=\"");
  write_str(sink, name);
  write_str(sink, "\"\r\n\r\n");
}

void write_field(ByteSink& sink, const char* boundary, const char* name,
                 const char* value) {
  write_part_header(sink, boundary, name);
  write_str(sink, value);
  write_str(sink, "\r\n");
}

}  // namespace

void format_boundary(const RoiUploadFields& fields, char* out) {
  std::snprintf(out, kBoundaryMaxLength + 1, "birdcall-%s",
                fields.client_upload_id);
}

void write_roi_upload_body(const RoiUploadFields& fields, const float* audio,
                           size_t sample_count, uint32_t sample_rate,
                           ByteSink& sink) {
  char boundary[kBoundaryMaxLength + 1];
  format_boundary(fields, boundary);

  char number[32];

  write_field(sink, boundary, "device_id", fields.device_id);
  write_field(sink, boundary, "client_upload_id", fields.client_upload_id);
  write_field(sink, boundary, "capture_session_id", fields.capture_session_id);

  std::snprintf(number, sizeof(number), "%u",
                static_cast<unsigned>(fields.snippet_sequence));
  write_field(sink, boundary, "snippet_sequence", number);

  write_field(sink, boundary, "capture_started_at", fields.capture_started_at);

  std::snprintf(number, sizeof(number), "%.4f", fields.roi_start_seconds);
  write_field(sink, boundary, "roi_start_seconds", number);

  std::snprintf(number, sizeof(number), "%.4f", fields.roi_end_seconds);
  write_field(sink, boundary, "roi_end_seconds", number);

  write_field(sink, boundary, "edge_processing_version",
              fields.edge_processing_version);
  write_field(sink, boundary, "edge_processing_metadata",
              fields.edge_processing_metadata);

  // audio_file part
  write_str(sink, "--");
  write_str(sink, boundary);
  write_str(sink, "\r\nContent-Disposition: form-data; name=\"audio_file\"; "
                  "filename=\"");
  write_str(sink, fields.client_upload_id);
  write_str(sink, ".wav\"\r\nContent-Type: audio/wav\r\n\r\n");

  uint8_t header[kWavHeaderBytes];
  write_wav_header(header, static_cast<uint32_t>(sample_count), sample_rate);
  sink.write(header, sizeof(header));

  // Encode in small chunks so no full-size PCM buffer is needed.
  constexpr size_t kChunkSamples = 256;
  uint8_t pcm[kChunkSamples * 2];
  for (size_t done = 0; done < sample_count; done += kChunkSamples) {
    const size_t n = sample_count - done < kChunkSamples
                         ? sample_count - done
                         : kChunkSamples;
    encode_pcm16(audio + done, n, pcm);
    sink.write(pcm, n * 2);
  }

  write_str(sink, "\r\n--");
  write_str(sink, boundary);
  write_str(sink, "--\r\n");
}

}  // namespace upload
