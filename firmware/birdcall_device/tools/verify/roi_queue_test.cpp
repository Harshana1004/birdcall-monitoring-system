// Desktop stress test for app::RoiQueue (the upload queue's ring
// allocator). Runs random reserve/commit/cancel/pop sequences and
// checks after every step that:
//   * every live ROI lies inside the pool and no two overlap,
//   * each ROI's samples are untouched until it is popped,
//   * entries come out in the order they were committed,
//   * a reservation only fails when there really is no room.
//
// Build and run (from firmware/birdcall_device):
//   g++ -std=c++17 -O2 -static -I src tools/verify/roi_queue_test.cpp src/app/roi_queue.cpp -o roi_queue_test
//   ./roi_queue_test

#include <cstdio>
#include <cstdlib>
#include <deque>
#include <random>
#include <vector>

#include "app/roi_queue.h"

namespace {

struct Live {
  size_t offset;
  size_t count;
  int16_t tag;  // every sample of the ROI is filled with this value
  uint32_t sequence;
};

int failures = 0;

void fail(const char* what, long step) {
  if (failures < 10) {
    std::printf("FAIL at step %ld: %s\n", step, what);
  }
  ++failures;
}

// True if `count` samples fit somewhere the ring allocator is allowed
// to use (after the newest entry, or at the pool start when wrapping).
bool could_fit(const std::deque<Live>& live, size_t pool, size_t count,
               size_t head) {
  if (live.empty()) {
    return count <= pool;
  }
  const size_t tail = live.front().offset;
  if (head > tail) {
    return pool - head >= count || count <= tail;
  }
  return tail - head >= count;
}

}  // namespace

int main() {
  constexpr size_t kPool = 50000;
  constexpr size_t kMaxEntries = 16;

  std::vector<int16_t> pool(kPool, 0);
  std::vector<app::QueuedRoi> entries(kMaxEntries);
  app::RoiQueue queue;
  queue.init(entries.data(), kMaxEntries, pool.data(), kPool);

  std::mt19937 rng(12345);
  std::deque<Live> live;
  uint32_t next_sequence = 0;
  uint32_t expected_pop = 0;
  int16_t next_tag = 1;
  size_t model_head = 0;
  long reservations = 0, rejections = 0, wraps = 0;

  for (long step = 0; step < 200000; ++step) {
    const int op = rng() % 10;

    if (op < 5) {
      // Producer: ROI sizes from tiny to a quarter of the pool.
      const size_t count = 1 + rng() % (kPool / 4);
      app::QueuedRoi* e = queue.reserve(count);

      const bool room = live.size() < kMaxEntries &&
                        could_fit(live, kPool, count,
                                  live.empty() ? 0 : model_head);
      if ((e != nullptr) != room) {
        fail(e ? "reserved without room" : "rejected despite room", step);
      }
      if (e == nullptr) {
        ++rejections;
        continue;
      }
      ++reservations;
      if (e->sample_count != count || e->pcm != pool.data() + e->offset ||
          e->offset + count > kPool) {
        fail("bad reservation geometry", step);
        continue;
      }
      if (!live.empty() && e->offset == 0 && model_head != 0) {
        ++wraps;
      }

      if (rng() % 8 == 0) {
        queue.cancel();
        continue;
      }
      const int16_t tag = next_tag++;
      if (next_tag == 0) next_tag = 1;
      for (size_t i = 0; i < count; ++i) e->pcm[i] = tag;
      e->snippet_sequence = next_sequence;
      queue.commit();
      live.push_back({e->offset, count, tag, next_sequence++});
      model_head = e->offset + count;
    } else if (op < 9) {
      // Consumer.
      app::QueuedRoi* e = queue.front();
      if ((e == nullptr) != live.empty()) {
        fail("front() disagrees with model", step);
        continue;
      }
      if (e == nullptr) continue;
      const Live& expect = live.front();
      if (e->snippet_sequence != expected_pop || e->offset != expect.offset) {
        fail("wrong entry at front", step);
      }
      for (size_t i = 0; i < expect.count; ++i) {
        if (e->pcm[i] != expect.tag) {
          fail("ROI audio was overwritten", step);
          break;
        }
      }
      queue.pop();
      live.pop_front();
      ++expected_pop;
      if (live.empty()) model_head = 0;
    }

    // Invariants over all live ROIs.
    if (queue.size() != live.size()) fail("size mismatch", step);
    for (size_t a = 0; a < live.size(); ++a) {
      if (live[a].offset + live[a].count > kPool) fail("out of pool", step);
      for (size_t b = a + 1; b < live.size(); ++b) {
        const bool overlap =
            live[a].offset < live[b].offset + live[b].count &&
            live[b].offset < live[a].offset + live[a].count;
        if (overlap) fail("two live ROIs overlap", step);
      }
    }
  }

  std::printf("reservations %ld, rejected (full) %ld, wraps %ld\n",
              reservations, rejections, wraps);
  std::printf(failures == 0 ? "PASS\n" : "%d failure(s)\n", failures);
  return failures == 0 ? 0 : 1;
}
