# Padding, temporal aggregation, noise gate and location filter

Produced by `evaluation_ea/run_padding_aggregation_eval.py` (2026-10-05)
with firmware DSP `esp32-dsp-1.1.0` (1 kHz-filtered upload). Following
these results, the firmware moved to `esp32-dsp-1.2.0`: unfiltered upload
and an x4 gate. `edge_reference.py` now models 1.2.0, so re-running the
main script reproduces the "unfiltered" numbers rather than "silence".
Full numbers: `metrics.csv` (every gate x padding x filter x selection
rule), `summary.csv` (ROI statistics).

## Setup

- **Data:** 21 x 1 h Western Amazon (Peru) dawn soundscapes, 14,798
  annotated events of known species (2,828 species-per-5-minute presences,
  790 species-per-recording pairs). **Not Sri Lankan birds**: relative
  differences between options carry over better than absolute numbers.
- **Device pipeline:** exactly what the ESP32 does: 16 kHz, consecutive
  10 s windows, the firmware DSP (`edge_reference.py`, bit-exact with the
  device): 1 kHz high-pass before detection, 2 x median extent, peak gate.
- **Peak gate** (`ROI_MIN_PEAK_FACTOR`): x8 (deployed), x4, x2 (= no gate
  beyond the 2 x median threshold).
- **Padding of ROIs < 3 s** (BirdNET's fixed input):
  - silence = today (BirdNET appends digital silence);
  - noise = noise synthesised from the ROI's quietest frames;
  - repeat = ROI tiled;
  - context = 3 s of real audio around the ROI (extra 4G data).
- **Raw:** BirdNET on the full recordings, no ROIs (upper bound).
- **Location filter:** BirdNET geo model at the site (approx. -12.53, -69.05;
  the dataset ships no coordinates) for each file's week, as deployed.
- **Metrics:**
  - events: same species, overlapping in time, one-to-one;
  - species present per 5-minute block;
  - species present per recording.

## ROI coverage

| Gate | ROIs | ROI audio / hour | < 3 s | Extra upload for "context" |
|---|---|---|---|---|
| x8 (deployed) | 927 | 1.6 min | 79 % | +50 % |
| x4 | 3,533 | 5.8 min | 81 % | +56 % |
| x2 | 8,390 | 12.0 min | 87 % | +75 % |

## Results (location filter on, threshold 0.25)

| | Species/5 min P | R | F1 | Species/recording P | R | F1 |
|---|---|---|---|---|---|---|
| Raw BirdNET | 0.704 | 0.570 | 0.630 | 0.712 | 0.618 | 0.662 |
| x2 silence | 0.711 | 0.137 | 0.230 | 0.642 | 0.186 | 0.289 |
| x2 noise | 0.661 | 0.121 | 0.205 | 0.571 | 0.167 | 0.259 |
| x2 repeat | 0.637 | 0.163 | 0.259 | 0.553 | 0.224 | 0.319 |
| x2 context | **0.727** | 0.156 | 0.257 | 0.678 | 0.210 | **0.321** |
| x4 silence | 0.698 | 0.079 | 0.142 | 0.635 | 0.119 | 0.200 |
| x4 context | 0.728 | 0.086 | 0.154 | 0.682 | 0.130 | 0.219 |
| x8 silence | 0.650 | 0.027 | 0.052 | 0.662 | 0.057 | 0.105 |
| x8 context | 0.639 | 0.028 | 0.053 | 0.681 | 0.059 | 0.109 |

## Findings

1. **ROI selection limits recall far more than anything after it.** In a
   dense dawn chorus the window median is the chorus itself, so few calls
   rise 2x above it. Even with no extra gate (x2) the device keeps 12 min
   per hour and finds 14 % of the 5-minute species presences, against
   57 % for raw BirdNET. The deployed x8 gate keeps 1.6 min per hour and
   finds 2.7 %. Each step of the gate trades upload volume for recall
   at nearly constant precision. x8 was tuned on a quiet room and is too
   strict for a busy soundscape.
2. **The location filter is a clear win.**
   - Precision rises in every configuration with no recall loss: raw
     species-per-recording precision goes from 0.563 to 0.712, and the
     device pipelines gain 7–18 points.
   - It removes out-of-range species and nothing else.
3. **Padding: real context is best, synthetic fill is not.**
   - Context raises both precision and recall over silence (x2:
     5-minute P 0.711 → 0.727, R 0.137 → 0.156; recording F1 0.289 →
     0.321). The cost is +50–75 % upload data.
   - Repeating the ROI raises recall about as much but lowers precision:
     BirdNET hears the call several times and becomes over-confident.
   - Matched noise is worse than silence on every metric.
   - Silence is a reasonable server-side default.
4. **Combining scores over time adds little beyond a lower threshold.**
   - The aggregation rules ("max ≥ 0.25 or N snippets ≥ 0.10/0.15 within
     60/300 s") land on almost the same precision/recall curve as a plain
     threshold.
   - Example, raw: threshold 0.25 F1 0.630 vs. 60 s "2 x ≥ 0.15" F1 0.631.
   - Device snippets are sparse, so repeated hits of the same species in
     a block are rare.
5. **Threshold.** For the device pipeline, F1 is higher at lower
   thresholds: x2 silence 5-minute F1 is 0.230 at 0.25, 0.272 at 0.15 and
   0.293 at 0.10. Precision drops from 0.71 to 0.59 and 0.48 along the
   way. Raw BirdNET is best around 0.25.

## Why the device pipeline loses recall (x2 gate)

Of the events raw BirdNET detects:

- 43 % have no ROI at all;
- 45 % are inside an ROI but missed on the snippet;
- 12 % are kept.

With the deployed x8 gate, 92 % have no ROI.

`run_snippet_degradation_eval.py` takes the same 3,000 clips (3 s of real
audio around x2 ROIs) and applies the device's processing one step at a
time. Of the events raw BirdNET detects inside those clips:

| Step | BirdNET still detects |
|---|---|
| Original 32 kHz audio, cut to the clip | 76 % |
| + resample to 16 kHz (device rate, nothing > 8 kHz) | 54 % |
| + causal 1 kHz high-pass (device filter) | **22 %** |
| + peak normalisation (= uploaded audio) | 21 % |

**The 1 kHz high-pass on the uploaded audio is the largest single loss.**
Only 7 % of events lie entirely below 1 kHz, so the loss comes from BirdNET
seeing audio unlike its (unfiltered) training data, not just from cut-off
low calls. The 16 kHz sample rate is second; normalisation does not matter.
Context and padding matter much less than both, which is why the
"context" variant helped only a little.

## Uploading unfiltered ROIs

`run_upload_filter_eval.py` keeps the same ROIs (detection still on the
1 kHz-filtered signal) and changes only the uploaded audio:

- hpf1000: today;
- hpf150: a gentle 4th-order 150 Hz high-pass;
- unfiltered: only the device's 20 Hz DC blocker.

All use silence padding; location filter on.

Raw-detected events inside an ROI that BirdNET finds on the snippet:

| Gate | hpf1000 | hpf150 | unfiltered |
|---|---|---|---|
| x8 | 18.6 % | 27.3 % | **37.5 %** |
| x4 | 21.7 % | 33.0 % | **43.9 %** |
| x2 | 20.7 % | 31.4 % | **41.8 %** |

| Gate | Upload | Threshold | Species/5 min P | R | F1 | Species/recording P | R | F1 |
|---|---|---|---|---|---|---|---|---|
| x2 | hpf1000 | 0.25 | 0.711 | 0.137 | 0.230 | 0.642 | 0.186 | 0.289 |
| x2 | hpf150 | 0.25 | 0.749 | 0.182 | 0.293 | 0.706 | 0.237 | 0.355 |
| x2 | unfiltered | 0.25 | 0.748 | **0.214** | **0.332** | 0.695 | 0.262 | 0.381 |
| x2 | unfiltered | 0.15 | 0.632 | **0.261** | **0.369** | 0.583 | 0.333 | **0.424** |
| x4 | hpf1000 | 0.25 | 0.698 | 0.079 | 0.142 | 0.635 | 0.119 | 0.200 |
| x4 | unfiltered | 0.25 | 0.757 | 0.128 | 0.218 | 0.711 | 0.177 | 0.284 |
| x8 | hpf1000 | 0.25 | 0.650 | 0.027 | 0.052 | 0.662 | 0.057 | 0.105 |
| x8 | unfiltered | 0.25 | 0.712 | 0.039 | 0.074 | 0.724 | 0.080 | 0.144 |

Uploading unfiltered ROIs doubles what BirdNET finds inside ROIs and raises
both recall (+40–60 % relative) and precision (+4–6 points) at every
gate, at no extra upload cost. Even a 150 Hz high-pass gives away a third
of that gain. Detection should keep using the 1 kHz-filtered signal (that
is what stops hum and wind creating ROIs), but the upload should be the
unfiltered (DC-blocked) audio.

## Concatenating snippets before BirdNET

`run_concat_eval.py` joins consecutive ROIs of a recording whose gaps are
<= 10 s or <= 60 s into one file (10 ms crossfades), runs BirdNET on the
joined files, and maps each 3 s window back to the real time of the ROI
audio inside it. Location filter on.

| Gate | Join | Threshold | Species/5 min P | R | F1 | Species/recording P | R | F1 |
|---|---|---|---|---|---|---|---|---|
| x2 | per snippet | 0.25 | 0.711 | 0.137 | 0.230 | 0.642 | 0.186 | 0.289 |
| x2 | concat 10 s | 0.25 | 0.728 | 0.129 | 0.220 | 0.700 | 0.177 | 0.283 |
| x2 | concat 60 s | 0.25 | 0.738 | 0.132 | 0.224 | 0.704 | 0.175 | 0.280 |
| x2 | per snippet | 0.15 | 0.594 | 0.176 | 0.272 | 0.540 | 0.258 | 0.349 |
| x2 | concat 10 s | 0.15 | 0.612 | 0.163 | 0.258 | 0.569 | 0.229 | 0.327 |
| x8 | per snippet | 0.25 | 0.650 | 0.027 | 0.052 | 0.662 | 0.057 | 0.105 |
| x8 | concat 10 s | 0.25 | 0.699 | 0.025 | 0.049 | 0.774 | 0.052 | 0.097 |

Concatenation raises precision by 2–11 points but lowers recall slightly;
F1 is unchanged or a little lower.

- Joined files fill BirdNET's 3 s windows with snippets from different
  moments instead of silence. That makes BirdNET more conservative.
- It also gives fewer windows, so fewer chances to detect a call.
- It cannot recover calls that never became ROIs, or calls damaged by the
  high-pass filter, which is where most of the gap to raw BirdNET is.

## Caveats

- One dataset (Amazon, dawn, dense chorus), which is close to the worst
  case for energy-based ROI detection. Quieter sites, such as the Sri
  Lankan balcony recordings, lose fewer calls.
- Recording levels differ from the INMP441, so the absolute
  -80 dBFS floor of the gate is not representative here; the
  x-median factor dominates.
- The site coordinates are approximate. The geo model is coarse, so this
  should matter little.
