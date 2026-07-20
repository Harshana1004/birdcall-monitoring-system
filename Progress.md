# BirdCall Monitoring System



# Phase 1 - Audio Preprocessing & Classification

## Objectives

- [x] Load and normalise audio recordings
- [x] Detect bird vocalisations using Short-Time Energy
- [x] Visualise waveform and detected RoIs
- [x] Extract detected RoIs
- [x] Apply high-pass noise filtering
- [x] Integrate BirdNET
- [x] Generate classification results

---


## Visual Outputs

### 1. Normalised Waveform

Shows the amplitude of the recording after normalisation.

![Waveform](outputs/waveforms/common_myna_01_waveform.png)

---

### 2. Short-Time Energy

Illustrates how the Short-Time Energy changes throughout the recording.

This graph was used to determine the detection threshold for identifying candidate bird calls.

![Energy](outputs/energy/common_myna_energy.png)

---

### 3. Detected Regions of Interest

Displays the waveform together with every detected RoI.

The highlighted regions correspond to the audio snippets extracted for BirdNET classification.

![RoIs](outputs/roi_plots/common_myna_detected_rois.png)

---

## RoI Extraction Experiments

Several extraction strategies were evaluated.

| Strategy | Result |
|----------|--------|
| Variable-length RoIs | Good baseline |
| Fixed 3-second windows (surrounding audio) | Lower classification performance |
| Exact RoIs padded to 3 seconds | Best overall performance |
| 2-second minimum duration | Similar results but lower average confidence |

### Final Decision

The final implementation extracts the exact detected RoI.

- RoIs shorter than 3 seconds are centre-padded with silence.
- RoIs longer than 3 seconds are preserved.
- BirdNET internally analyses long recordings using multiple 3-second windows.

This approach preserves the detected bird vocalisation while avoiding unrelated surrounding audio.

---

## BirdNET Classification


Outputs:

- Filtered audio snippets
- Classification CSV
- Species predictions
- Confidence scores

---

