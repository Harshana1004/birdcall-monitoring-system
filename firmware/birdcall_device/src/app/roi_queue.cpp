#include "app/roi_queue.h"

namespace app {

void RoiQueue::init(QueuedRoi* entries, size_t max_entries, int16_t* pool,
                    size_t pool_samples) {
  entries_ = entries;
  max_entries_ = max_entries;
  pool_ = pool;
  pool_samples_ = pool_samples;
  first_ = 0;
  count_ = 0;
  head_ = 0;
  pending_ = false;
}

QueuedRoi* RoiQueue::reserve(size_t sample_count) {
  if (pending_ || sample_count == 0 || sample_count > pool_samples_ ||
      count_ + 1 > max_entries_) {
    return nullptr;
  }

  size_t offset;
  if (count_ == 0) {
    offset = 0;  // empty: start from the beginning of the pool
  } else {
    // Live audio occupies [tail, head) when it has not wrapped, or
    // [tail, end) + [0, head) when it has.
    const size_t tail = entries_[first_].offset;
    if (head_ > tail) {
      if (pool_samples_ - head_ >= sample_count) {
        offset = head_;
      } else if (sample_count <= tail) {
        offset = 0;  // wrap, skipping the short tail of the pool
      } else {
        return nullptr;
      }
    } else {
      if (tail - head_ >= sample_count) {
        offset = head_;
      } else {
        return nullptr;
      }
    }
  }

  QueuedRoi& entry = entries_[(first_ + count_) % max_entries_];
  entry.offset = offset;
  entry.pcm = pool_ + offset;
  entry.sample_count = sample_count;
  entry.attempts = 0;

  pending_saved_head_ = head_;
  head_ = offset + sample_count;
  pending_ = true;
  return &entry;
}

void RoiQueue::commit() {
  if (pending_) {
    pending_ = false;
    ++count_;
  }
}

void RoiQueue::cancel() {
  if (pending_) {
    pending_ = false;
    head_ = pending_saved_head_;
  }
}

QueuedRoi* RoiQueue::front() {
  return count_ == 0 ? nullptr : &entries_[first_];
}

void RoiQueue::pop() {
  if (count_ == 0) {
    return;
  }
  first_ = (first_ + 1) % max_entries_;
  --count_;
  if (count_ == 0 && !pending_) {
    head_ = 0;
  }
}

size_t RoiQueue::used_samples() const {
  if (count_ == 0) {
    return 0;
  }
  const size_t tail = entries_[first_].offset;
  return head_ > tail ? head_ - tail : pool_samples_ - tail + head_;
}

}  // namespace app
