# BirdCall Monitoring System

A solar-powered embedded IoT system for autonomous bird call monitoring and species identification in remote environments.

The system continuously monitors ambient audio using an ESP32-S3 based recording node deployed in the field. Rather than transmitting continuous audio, the embedded device performs lightweight local processing to detect potential bird vocalizations, extracts short audio snippets, temporarily stores them on a MicroSD card, and uploads them to a cloud backend over a 4G LTE cellular network using a REST API.

The backend performs audio processing, bird species identification using BirdNET, stores detections in a PostgreSQL database, and visualizes results through a web dashboard.

---

# Objectives

* Continuously monitor bird vocalizations in remote environments.
* Minimize storage and cellular data usage using on-device event detection.
* Automatically identify bird species using machine learning.
* Provide researchers with a centralized dashboard for monitoring biodiversity.
* Design a scalable architecture suitable for multiple deployed recording nodes.

---

# Proposed System

The project is divided into two major components:

## Embedded Recorder

Hardware

* ESP32-S3 Development Board (with PSRAM)
* INMP441 I2S MEMS Microphone
* SIMA7670C FS-MCore 4G LTE Module
* SPI MicroSD Card Module
* 32GB MicroSD Card
* 18650 Li-Ion Battery
* Solar Panel + Battery Charging Circuit

Responsibilities

* Continuously monitor ambient audio.
* Detect Regions of Interest (RoI) containing bird vocalizations.
* Save short audio snippets to the MicroSD card.
* Maintain a reliable upload queue using local storage.
* Upload snippets and metadata to the backend using HTTPS.
* Retry uploads automatically when network connectivity is unavailable.
* Operate using low-power techniques for long-term deployment.

---

## Cloud Backend

Responsibilities

* Receive uploaded recordings.
* Perform noise reduction.
* Segment bird calls.
* Identify bird species using BirdNET.
* Store recordings and detections.
* Provide REST APIs for visualization and analytics.
* Display results through a web dashboard.

---

# High-Level Architecture

```text
                        Forest Environment
                               │
                        Bird Vocalization
                               │
                               ▼
                     ESP32-S3 Recording Node
         ┌────────────────────────────────────────┐
         │ • INMP441 I2S Microphone               │
         │ • Region of Interest Detection         │
         │ • MicroSD Upload Queue                 │
         │ • SIMA7670C LTE Module                 │
         │ • Battery & Solar Power                │
         └────────────────────────────────────────┘
                               │
                  HTTPS REST API (4G LTE Network)
                               │
                               ▼
                     FastAPI Backend Server
                               │
                   Store Audio & Metadata
                               │
                               ▼
                    Audio Processing Pipeline
      Noise Reduction → Segmentation → BirdNET
                               │
                               ▼
                       PostgreSQL Database
                               │
                               ▼
                     React Monitoring Dashboard
```

---

# Planned Software Architecture

```text
birdcall-monitoring-system/

├── backend/            # FastAPI backend
├── dashboard/          # React dashboard
├── data/
│   ├── raw/
│   ├── processed/
│   ├── snippets/
│   └── test_audio/
├── docs/
├── embedded/           # ESP32 firmware
├── models/
│   └── birdnet/
├── pipeline/
│   ├── audio_loader.py
│   ├── roi_detector.py
│   ├── noise_filter.py
│   ├── segmenter.py
│   ├── classifier.py
│   └── pipeline.py
├── tests/
├── README.md
└── requirements.txt
```

---

# Development Plan

## Phase 1 – Audio Processing Pipeline

Goal:

Develop and validate the complete audio processing pipeline using prerecorded bird recordings.

Tasks:

* Load audio files.
* Normalize audio.
* Detect Regions of Interest (RoI).
* Extract audio snippets.
* Apply noise reduction.
* Segment bird vocalizations.
* Integrate BirdNET for species identification.

Deliverable:

A software pipeline capable of identifying bird species from prerecorded audio.

---

## Phase 2 – Backend Development

Goal:

Develop the cloud backend responsible for receiving recordings and managing processing.

Tasks:

* FastAPI REST API
* Audio upload endpoint
* Metadata handling
* Audio storage
* Processing queue
* PostgreSQL integration

Deliverable:

Backend capable of receiving recordings from embedded devices.

---

## Phase 3 – Database & Storage

Goal:

Design persistent storage for recordings and detections.

Tasks:

* Database schema
* Recording metadata
* Detection records
* Species information
* Storage management

Deliverable:

Persistent storage for all processed detections.

---

## Phase 4 – Dashboard

Goal:

Visualize system outputs.

Features:

* Bird detections
* Timeline view
* Audio playback
* Device status
* Detection history
* Statistics and analytics

Deliverable:

Interactive monitoring dashboard.

---

## Phase 5 – Embedded Device

Goal:

Develop the ESP32 firmware.

Tasks:

* Continuous audio acquisition
* Region of Interest (RoI) detection
* MicroSD queue management
* HTTPS REST API client
* LTE communication using the SIMA7670C module
* Reliable upload mechanism with automatic retry
* Device health monitoring
* Low-power operation

Deliverable:

Fully functional autonomous recording node.

---

## Phase 6 – Power Management & Deployment

Goal:

Prepare the system for long-term field deployment.

Tasks:

* Battery management
* Solar charging
* Low-power operation
* Sleep scheduling
* Outdoor field testing
* Reliability testing

Deliverable:

Self-powered embedded bird monitoring station.

---

# Technology Stack

## Embedded

* ESP32-S3 (with PSRAM)
* PlatformIO
* Arduino Framework
* SIMA7670C FS-MCore 4G LTE Module
* INMP441 I2S MEMS Microphone
* SPI MicroSD Card Module

## Backend

* Python
* FastAPI
* SQLAlchemy
* PostgreSQL

## Audio Processing

* NumPy
* SciPy
* Librosa
* BirdNET

## Frontend

* React
* Tailwind CSS

## Communication

* HTTPS REST API
* 4G LTE Cellular Network
