"""
Run the backend's AudioProcessingService on a WAV dumped by
tools/capture_wav.py and compare its ROIs with what the device
reported for the same samples.

    backend/.venv/Scripts/python firmware/birdcall_device/tools/verify/compare_capture.py capture.wav
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO / "backend"))

from src.services.audio_processing import AudioProcessingService  # noqa: E402


def main() -> int:
    wav = Path(sys.argv[1])
    device_text = wav.with_suffix(".device.txt").read_text()

    service = AudioProcessingService()
    audio, _ = service.load_audio(wav)
    normalized = service.normalize_audio(audio)
    regions, _, threshold = service.detect_regions(normalized)

    device_threshold = float(re.search(r"threshold=(\S+)", device_text).group(1))
    device_rois = [
        (float(a), float(b))
        for a, b in re.findall(r"roi \d+: (\S+) s -> (\S+) s", device_text)
    ]

    print(f"threshold  backend {threshold:.6g}   device {device_threshold:.6g}")
    print(f"rois       backend {len(regions)}   device {len(device_rois)}")
    for i in range(max(len(regions), len(device_rois))):
        b = f"{regions[i].start_time:7.3f} -> {regions[i].end_time:7.3f}" if i < len(regions) else " " * 18
        d = f"{device_rois[i][0]:7.3f} -> {device_rois[i][1]:7.3f}" if i < len(device_rois) else ""
        print(f"  {i}: backend {b}   device {d}")

    same = len(regions) == len(device_rois) and all(
        abs(r.start_time - d[0]) < 0.011 and abs(r.end_time - d[1]) < 0.011
        for r, d in zip(regions, device_rois)
    )
    print("MATCH" if same else "MISMATCH")
    return 0 if same else 1


if __name__ == "__main__":
    raise SystemExit(main())
