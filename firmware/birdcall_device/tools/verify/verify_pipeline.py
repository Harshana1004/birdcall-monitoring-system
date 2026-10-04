"""
Verify dsp::process_capture() against the Python reference on
synthetic signals.

Reference = edge_reference.edge_pipeline(): the backend's own
AudioProcessingService steps with the documented on-device
deviations applied (high-pass before detection, peak gate, no 3 s
padding, causal sosfilt).

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

HERE = Path(__file__).resolve().parent
FIRMWARE = HERE.parents[1]
REPO = FIRMWARE.parents[1]

sys.path.insert(0, str(REPO / "backend"))

from edge_reference import edge_pipeline  # noqa: E402

SAMPLE_RATE = 16000


def make_signal() -> np.ndarray:
    """12 s of low noise with bird-like bursts that exercise merge,
    min-duration discard, the peak gate, edge clipping and a long
    (>3 s) ROI."""
    rng = np.random.default_rng(1234)
    n = 12 * SAMPLE_RATE
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
    burst(9.6, 0.4, 3000, 3200, 0.012)  # ~4x the median: above 2x,
                                         # rejected by the peak gate
    burst(11.7, 0.3, 3500, 3600, 0.5)   # clipped at end boundary
    return audio.astype(np.float32)


def run_harness(audio: np.ndarray, work: Path):
    exe = work / "pipeline_harness.exe"
    sources = [str(HERE / "pipeline_harness.cpp")] + [
        str(p) for p in sorted((FIRMWARE / "src" / "dsp").glob("*.cpp"))
    ]
    subprocess.run(
        ["g++", "-std=c++17", "-O2", "-static", "-Wall", "-Wextra",
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


def compare(name: str, audio: np.ndarray, work: Path, check,
            expect_rois: int | None = None, expect_rejected: int | None = None):
    print(name)
    ref = edge_pipeline(audio.copy())
    info, rois = run_harness(audio, work)

    check(info["status"] == 0, f"status = {int(info['status'])}")
    check(info["frames"] == ref.frames, f"frames {int(info['frames'])} vs {ref.frames}")

    def close(key: str, ref_value: float, tol: float = 1e-4):
        value = info[key]
        if np.isinf(ref_value):
            check(np.isinf(value), f"{key} {value} vs inf")
            return
        rel = abs(value - ref_value) / max(abs(ref_value), 1e-30)
        check(rel < tol, f"{key} {value:.6g} vs {ref_value:.6g} (rel {rel:.1e})")

    close("threshold", ref.threshold)
    close("peak_threshold", ref.peak_threshold)
    close("band_peak", ref.band_peak)
    check(abs(info["noise_floor_dbfs"] - ref.noise_floor_dbfs) < 0.01,
          f"noise floor {info['noise_floor_dbfs']:.2f} vs {ref.noise_floor_dbfs:.2f} dBFS")
    check(abs(info["loudest_dbfs"] - ref.loudest_dbfs) < 0.01,
          f"loudest {info['loudest_dbfs']:.2f} vs {ref.loudest_dbfs:.2f} dBFS")
    check(info["rejected"] == ref.rejected,
          f"rejected regions {int(info['rejected'])} vs {ref.rejected}")
    check(len(rois) == len(ref.rois), f"roi count {len(rois)} vs {len(ref.rois)}")
    if expect_rois is not None:
        check(len(rois) == expect_rois, f"expected {expect_rois} ROIs, got {len(rois)}")
    if expect_rejected is not None:
        check(info["rejected"] == expect_rejected,
              f"expected {expect_rejected} rejected, got {int(info['rejected'])}")

    for (i, s, e, a), (ri, rs, re, ra) in zip(rois, ref.rois):
        label = f"roi {ri} [{rs:.3f}s, {re:.3f}s]"
        check(i == ri and abs(s - rs) < 1e-5 and abs(e - re) < 1e-5,
              f"{label} bounds")
        check(len(a) == len(ra), f"{label} samples {len(a)} vs {len(ra)}")
        if len(a) == len(ra):
            err = float(np.max(np.abs(a - ra)))
            check(err < 1e-4, f"{label} max abs error {err:.2e}")


def main() -> int:
    audio = make_signal()
    failures = []

    def check(ok: bool, message: str):
        print(("  ok   " if ok else "  FAIL ") + message)
        if not ok:
            failures.append(message)

    with tempfile.TemporaryDirectory() as tmp:
        # Bursts: merged pair, long ROI and the two edge-clipped ones
        # survive; the quiet burst is gated; the short one is too short.
        compare("synthetic capture", audio, Path(tmp), check,
                expect_rois=4, expect_rejected=1)
        # The same capture 80 dB quieter is below the absolute floor.
        compare("same capture at -80 dB", audio * np.float32(1e-4), Path(tmp),
                check, expect_rois=0)

    print("PASS" if not failures else f"{len(failures)} check(s) failed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
