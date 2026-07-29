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

Shows how the Short-Time Energy changes throughout the recording.

This graph was used to determine the detection threshold for identifying possible bird calls.

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
| Variable-length RoIs | Good |
| Fixed 3-second windows (surrounding audio) | Lower classification performance |
| Exact RoIs padded to 3 seconds | Best overall performance |
| 2-second minimum duration | Similar results but lower average confidence |

### Final Decision

The final implementation extracts the exact detected RoI.

- RoIs shorter than 3 seconds are padded with silence.
- RoIs longer than 3 seconds are unchanged.
- BirdNET internally analyses long recordings using multiple 3 second intervals.

This maintained the detected bird vocalisation while avoiding unrelated surrounding audio.

---

## BirdNET Classification


Outputs:

- Filtered audio snippets
- Classification CSV
- Species predictions
- Confidence scores

---

---

# Phase 2 - Backend API & Database

## Objectives

### Project Setup

* [x] FastAPI project structure
* [x] PostgreSQL integration
* [x] SQLAlchemy Async ORM
* [x] Alembic migrations
* [x] Configuration management
* [x] Global exception handling

---

### Device Management

* [x] Device database model
* [x] Validation
* [x] Repository pattern
* [x] Service layer

---

### Recording Management

* [x] Recording database model
* [x] Secure audio upload endpoint
* [x] WAV metadata extraction
* [x] Duplicate upload detection
* [x] Capture session support
* [x] ROI metadata support
* [x] Recording retrieval
* [x] Recording deletion

---

### BirdNET Processing Pipeline

Processing workflow:

```text
ROI Upload
    ↓
Recording stored (Pending)
    ↓
Background Task
    ↓
BirdNET Analysis
    ↓
Detection Storage
    ↓
Recording Completed
```

Completed:

* [x] BirdNET service
* [x] Automatic background processing
* [x] Recording processing lifecycle
* [x] Failed processing handling

---

### Detection Management

* [x] Detection database model
* [x] Detection repository
* [x] Detection service
* [x] Detection schemas
* [x] Detection storage
* [x] Detection retrieval API
* [x] Recording-specific detection API

---

## Backend REST API

### Devices

* [x] POST `/api/v1/devices`
* [x] GET `/api/v1/devices`
* [x] GET `/api/v1/devices/{id}`
* [x] PATCH `/api/v1/devices/{id}`
* [x] DELETE `/api/v1/devices/{id}`

### Recordings

* [x] POST `/api/v1/recordings`
* [x] GET `/api/v1/recordings`
* [x] GET `/api/v1/recordings/{id}`
* [x] GET `/api/v1/recordings/{id}/detections`
* [x] DELETE `/api/v1/recordings/{id}`

### Detections

* [x] GET `/api/v1/detections`
* [x] GET `/api/v1/detections/{id}`

### System

* [x] GET `/health`
* [x] GET `/ready`

---

## Current Backend Status

### Completed

* ✔ Asynchronous FastAPI backend
* ✔ PostgreSQL database integration
* ✔ Device management module
* ✔ Recording upload pipeline
* ✔ Audio validation and metadata extraction
* ✔ Background BirdNET processing
* ✔ Detection persistence
* ✔ Detection retrieval APIs
* ✔ Repository–Service architecture
* ✔ Centralised exception handling

---

## Next Development Milestones

* [ ] Species statistics and analytics endpoints
* [ ] Recording download endpoint
* [ ] Authentication and authorization
* [ ] Frontend dashboard integration
* [ ] ESP32 end-to-end integration
* [ ] Production deployment
* [ ] Monitoring and logging improvements
