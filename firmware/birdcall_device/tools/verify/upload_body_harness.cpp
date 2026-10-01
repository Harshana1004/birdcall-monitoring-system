// Desktop harness: runs dsp::process_capture() over a raw float32
// signal, then builds the POST /api/v1/recordings multipart body
// for every ROI and streams them to stdout, each framed as
//   "BODY <boundary> <counted_length>" newline, then the body bytes.
// verify_upload_body.py checks the bodies (and can post them to a
// local backend). Not part of the firmware build.
//
// usage: upload_body_harness <device_id> <unix_ms> < signal.f32

#include <cstdio>
#include <cstdlib>
#include <vector>

#ifdef _WIN32
#include <fcntl.h>
#include <io.h>
#endif

#include "config.h"
#include "dsp/dsp_pipeline.h"
#include "upload/edge_metadata.h"
#include "upload/roi_upload.h"
#include "upload/uuid.h"
#include "upload/wav_writer.h"

namespace {

class StdoutSink : public upload::ByteSink {
 public:
  void write(const uint8_t* data, size_t length) override {
    std::fwrite(data, 1, length, stdout);
  }
};

class VectorSink : public upload::ByteSink {
 public:
  void write(const uint8_t* data, size_t length) override {
    bytes.insert(bytes.end(), data, data + length);
  }
  std::vector<uint8_t> bytes;
};

// Deterministic bytes so test output is reproducible.
void fake_random(uint8_t out[16], uint32_t seed) {
  for (int i = 0; i < 16; ++i) {
    seed = seed * 1664525u + 1013904223u;
    out[i] = static_cast<uint8_t>(seed >> 24);
  }
}

}  // namespace

int main(int argc, char** argv) {
  if (argc != 3) {
    std::fprintf(stderr, "usage: %s device_id unix_ms < signal.f32\n",
                 argv[0]);
    return 2;
  }
  const char* device_id = argv[1];

#ifdef _WIN32
  _setmode(_fileno(stdin), _O_BINARY);
  _setmode(_fileno(stdout), _O_BINARY);
#endif

  std::vector<float> audio;
  float sample;
  while (std::fread(&sample, sizeof(float), 1, stdin) == 1) {
    audio.push_back(sample);
  }

  const size_t frames = dsp::pipeline_frame_count(audio.size());
  std::vector<float> energy(frames), smoothed(frames), arena(audio.size());
  std::vector<dsp::RegionOfInterest> regions(frames / 2 + 1);
  std::vector<dsp::ProcessedRoi> rois(64);
  const dsp::PipelineWorkspace ws{energy.data(),  smoothed.data(),
                                  frames,         regions.data(),
                                  regions.size(), arena.data(),
                                  arena.size()};
  const dsp::PipelineResult result = dsp::process_capture(
      audio.data(), audio.size(), ws, rois.data(), rois.size());

  char metadata[1024];
  if (upload::format_edge_metadata(metadata, sizeof(metadata), result) == 0) {
    std::fprintf(stderr, "metadata buffer too small\n");
    return 1;
  }

  char started_at[upload::kIso8601Length + 1];
  upload::format_iso8601_utc(std::strtoll(argv[2], nullptr, 10), started_at);

  uint8_t rnd[16];
  char session_id[upload::kUuidStringLength + 1];
  fake_random(rnd, 1);
  upload::format_uuid_v4(rnd, session_id);

  for (size_t i = 0; i < result.roi_count; ++i) {
    const dsp::ProcessedRoi& roi = rois[i];

    char upload_id[upload::kUuidStringLength + 1];
    fake_random(rnd, 100 + static_cast<uint32_t>(i));
    upload::format_uuid_v4(rnd, upload_id);

    const upload::RoiUploadFields fields{
        device_id,
        upload_id,
        session_id,
        static_cast<uint32_t>(i),
        started_at,
        roi.region.start_time_seconds,
        roi.region.end_time_seconds,
        EDGE_PROCESSING_VERSION,
        metadata};

    upload::CountingSink counter;
    upload::write_roi_upload_body(fields, roi.audio, roi.sample_count,
                                  SAMPLE_RATE_HZ, counter);

    char boundary[upload::kBoundaryMaxLength + 1];
    upload::format_boundary(fields, boundary);

    // The continuous-mode queue stores ROIs as PCM16 (to_pcm16) and
    // uploads from that; it must yield exactly the same bytes.
    std::vector<int16_t> pcm(roi.sample_count);
    for (size_t k = 0; k < roi.sample_count; ++k) {
      pcm[k] = upload::to_pcm16(roi.audio[k]);
    }
    VectorSink from_float, from_pcm16;
    upload::write_roi_upload_body(
        fields, upload::RoiAudio{roi.audio, nullptr, roi.sample_count,
                                 SAMPLE_RATE_HZ},
        from_float);
    upload::write_roi_upload_body(
        fields, upload::RoiAudio{nullptr, pcm.data(), roi.sample_count,
                                 SAMPLE_RATE_HZ},
        from_pcm16);
    if (from_float.bytes != from_pcm16.bytes) {
      std::fprintf(stderr, "roi %zu: PCM16 path differs from float path\n",
                   i);
      return 3;
    }

    std::printf("BODY %s %zu\n", boundary, counter.total);
    StdoutSink sink;
    upload::write_roi_upload_body(fields, roi.audio, roi.sample_count,
                                  SAMPLE_RATE_HZ, sink);
  }

  std::fflush(stdout);
  return 0;
}
