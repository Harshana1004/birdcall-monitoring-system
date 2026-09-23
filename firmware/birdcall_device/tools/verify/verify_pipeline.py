"""
Verify dsp::process_capture() against the backend's
AudioProcessingService on a synthetic signal.

Reference = the backend's own normalize/detect_regions, then exact
ROI extraction (no 3 s padding) and causal scipy sosfilt -- i.e.
the reference pipeline with the two documented on-device
deviations applied.

Run from the repo root with the backend venv:

    backend/.venv/Scripts/python firmware/birdcall_device/tools/verify/verify_pipeline.py

Needs g++ on PATH.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from scipy.signal import butter, sosfilt

HERE = Path(__file__).resolve().parent
FIRMWARE = HERE.parents[1]
REPO = FIRMWARE.parents[1]

sys.path.insert(0, str(REPO / "backend"))

from src.services.audio_processing import AudioProcessingService  # noqa: E402

SAMPLE_RATE = 16000


def make_signal() -> np.ndarray:
    """10 s of low noise with bird-like bursts that exercise merge,
    min-duration discard, edge clipping and a long (>3 s) ROI."""
    rng = np.random.default_rng(1234)
    n = 10 * SAMPLE_RATE
    t = np.arange(n) / SAMPLE_RATE
    audio = 0.002 * rng.standard_normal(n)

    def burst(start: float, dur: float, f0: float, f1: float, amp: float):
        i0, i1 = int(start * SAMPLE_RATE), int((start + dur) * SAMPLE_RATE)
        tt = t[i0:i1] - start
        freq = f0 + (f1 - f0) * tt / dur
        phase = 2 * np.pi * np.cumsum(freq) / SAMPLE_RATE
        env = np.hanning(i1 - i0)
        audio[i0:i1] += amp * env * np.sin(phase)

    burst(0.05, 0.6, 3000, 4500, 0.5)   # clipped at start boundary
    burst(1.5, 0.4, 2500, 3500, 0.6)    # these two merge (gap < 0.5 s)
    burst(2.1, 0.5, 3000, 2000, 0.4)
    burst(3.5, 0.12, 4000, 4000, 0.3)   # too short -> discarded
    burst(5.0, 3.8, 1800, 5000, 0.35)   # long ROI, must not be truncated
    audio[int(5.0 * SAMPLE_RATE):int(8.8 * SAMPLE_RATE)] += (
        0.05 * np.sin(2 * np.pi * 300 * t[int(5.0 * SAMPLE_RATE):int(8.8 * SAMPLE_RATE)])
    )                                    # low-frequency hum for the HPF
    burst(9.7, 0.3, 3500, 3600, 0.5)    # clipped at end boundary
    return audio.astype(np.float32)


def reference(audio: np.ndarray):
    service = AudioProcessingService()
    normalized = service.normalize_audio(audio)
    regions, smoothed, threshold = service.detect_regions(normalized)
    sos = butter(4, 1000.0 / (SAMPLE_RATE / 2), btype="highpass", output="sos")

    rois = []
    for index, region in enumerate(regions):
        s = max(0, int(round(region.start_time * SAMPLE_RATE)))
        e = min(len(normalized), int(round(region.end_time * SAMPLE_RATE)))
        if e <= s:
            continue
        seg = sosfilt(sos, normalized[s:e]).astype(np.float32)
        rois.append((index, region.start_time, region.end_time, seg))
    return len(smoothed), threshold, rois


def run_harness(audio: np.ndarray, work: Path):
    exe = work / "pipeline_harness.exe"
    sources = [str(HERE / "pipeline_harness.cpp")] + [
        str(p) for p in sorted((FIRMWARE / "src" / "dsp").glob("*.cpp"))
    ]
    subprocess.run(
        ["g++", "-std=c++17", "-O2", "-Wall", "-Wextra",
         "-I", str(FIRMWARE / "include"), "-I", str(FIRMWARE / "src"),
         *sources, "-o", str(exe)],
        check=True,
    )
    signal, meta, out = work / "signal.f32", work / "meta.txt", work / "rois.f32"
    audio.tofile(signal)
    subprocess.run([str(exe), str(signal), str(meta), str(out)], check=True)

    info, rois = {}, []
    samples = np.fromfile(out, dtype=np.float32)
    offset = 0
    for line in meta.read_text().splitlines():
        parts = line.split()
        if parts[0] == "roi":
            count = int(parts[4])
            rois.append((int(parts[1]), float(parts[2]), float(parts[3]),
                         samples[offset:offset + count]))
            offset += count
        else:
            info[parts[0]] = float(parts[1])
    return info, rois


def main() -> int:
    audio = make_signal()
    ref_frames, ref_threshold, ref_rois = reference(audio.copy())

    with tempfile.TemporaryDirectory() as tmp:
        info, rois = run_harness(audio, Path(tmp))

    failures = []

    def check(ok: bool, message: str):
        print(("  ok   " if ok else "  FAIL ") + message)
        if not ok:
            failures.append(message)

    check(info["status"] == 0, f"status = {int(info['status'])}")
    check(info["frames"] == ref_frames,
          f"frames {int(info['frames'])} vs {ref_frames}")
    rel = abs(info["threshold"] - ref_threshold) / ref_threshold
    check(rel < 1e-5, f"threshold {info['threshold']:.6g} vs {ref_threshold:.6g} (rel {rel:.1e})")
    check(len(rois) == len(ref_rois), f"roi count {len(rois)} vs {len(ref_rois)}")

    for (i, s, e, a), (ri, rs, re, ra) in zip(rois, ref_rois):
        label = f"roi {ri} [{rs:.3f}s, {re:.3f}s]"
        check(i == ri and abs(s - rs) < 1e-5 and abs(e - re) < 1e-5,
              f"{label} bounds")
        check(len(a) == len(ra), f"{label} samples {len(a)} vs {len(ra)}")
        if len(a) == len(ra):
            err = float(np.max(np.abs(a - ra)))
            check(err < 1e-4, f"{label} max abs error {err:.2e}")

    print("PASS" if not failures else f"{len(failures)} check(s) failed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
