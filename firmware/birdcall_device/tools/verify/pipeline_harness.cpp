// Desktop harness: runs dsp::process_capture() over a raw float32
// signal and dumps the result for verify_pipeline.py to compare
// against the Python backend. Not part of the firmware build.
//
// usage: pipeline_harness <signal.f32> <meta.txt> <rois.f32>

#include <cstdio>
#include <vector>

#include "dsp/dsp_pipeline.h"

int main(int argc, char** argv) {
  if (argc != 4) {
    std::fprintf(stderr, "usage: %s signal.f32 meta.txt rois.f32\n", argv[0]);
    return 2;
  }

  std::FILE* in = std::fopen(argv[1], "rb");
  if (in == nullptr) {
    std::perror("signal");
    return 1;
  }
  std::vector<float> audio;
  float sample;
  while (std::fread(&sample, sizeof(float), 1, in) == 1) {
    audio.push_back(sample);
  }
  std::fclose(in);

  const size_t frames = dsp::pipeline_frame_count(audio.size());
  std::vector<float> energy(frames), smoothed(frames), arena(audio.size());
  std::vector<dsp::RegionOfInterest> regions(frames / 2 + 1);
  std::vector<dsp::ProcessedRoi> rois(64);

  const dsp::PipelineWorkspace ws{energy.data(),  smoothed.data(),
                                  frames,         regions.data(),
                                  regions.size(), arena.data(),
                                  arena.size()};

  const dsp::PipelineResult r =
      dsp::process_capture(audio.data(), audio.size(), ws, rois.data(),
                           rois.size());

  std::FILE* meta = std::fopen(argv[2], "w");
  std::FILE* out = std::fopen(argv[3], "wb");
  std::fprintf(meta, "status %d\nframes %zu\nthreshold %.9g\nrois %zu\n",
               static_cast<int>(r.status), r.frame_count, r.energy_threshold,
               r.roi_count);
  std::fprintf(meta,
               "peak_threshold %.9g\nband_peak %.9g\nnoise_floor_dbfs %.9g\n"
               "loudest_dbfs %.9g\nrejected %zu\n",
               r.peak_threshold, r.band_peak, r.noise_floor_dbfs,
               r.loudest_dbfs, r.rejected_region_count);
  for (size_t i = 0; i < r.roi_count; ++i) {
    const dsp::ProcessedRoi& p = rois[i];
    std::fprintf(meta, "roi %u %.9g %.9g %zu\n", p.index,
                 p.region.start_time_seconds, p.region.end_time_seconds,
                 p.sample_count);
    std::fwrite(p.audio, sizeof(float), p.sample_count, out);
  }
  std::fclose(meta);
  std::fclose(out);
  return 0;
}
