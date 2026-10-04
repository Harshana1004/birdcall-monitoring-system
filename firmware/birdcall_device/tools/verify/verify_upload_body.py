"""
Check the multipart bodies the firmware builds for
POST /api/v1/recordings.

Runs the real firmware code (dsp + upload modules, compiled with
g++) on a capture WAV, then for every ROI body:

  * Content-Length from the counting pass matches the bytes written
  * it parses as multipart/form-data with exactly the backend's fields
  * the fields pass the backend's own RecordingUploadMetadata schema
  * edge_processing_metadata is a JSON object under the size limit
  * the WAV is mono 16 kHz PCM16, its duration matches the ROI
    interval within the backend's tolerance, and its samples match
    the Python reference (edge_reference.py) to within PCM16
    rounding

With --post URL --device-id UUID it also POSTs each body to a
running backend and prints the response.

    backend/.venv/Scripts/python firmware/birdcall_device/tools/verify/verify_upload_body.py firmware/birdcall_device/capture_2.wav
"""

from __future__ import annotations

import argparse
import io
import json
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from email.parser import BytesParser
from email.policy import HTTP
from pathlib import Path

import numpy as np
import soundfile as sf

HERE = Path(__file__).resolve().parent
FIRMWARE = HERE.parents[1]
REPO = FIRMWARE.parents[1]
sys.path.insert(0, str(REPO / "backend"))

from src.api.schemas import RecordingUploadMetadata  # noqa: E402
from src.core.config import settings  # noqa: E402
from edge_reference import edge_pipeline  # noqa: E402

EXPECTED_FIELDS = [
    "device_id", "client_upload_id", "capture_session_id",
    "snippet_sequence", "capture_started_at", "roi_start_seconds",
    "roi_end_seconds", "edge_processing_version",
    "edge_processing_metadata", "audio_file",
]
PLACEHOLDER_DEVICE = "00000000-0000-0000-0000-000000000000"


def reference_rois(audio: np.ndarray, sr: int) -> list[np.ndarray]:
    return [samples for _, _, _, samples in edge_pipeline(audio, sr).rois]


def parse_multipart(body: bytes, boundary: str) -> dict[str, tuple[bytes, dict]]:
    head = f"Content-Type: multipart/form-data; boundary={boundary}\r\n\r\n".encode()
    message = BytesParser(policy=HTTP).parsebytes(head + body)
    parts = {}
    for part in message.iter_parts():
        name = part.get_param("name", header="content-disposition")
        parts[name] = (part.get_payload(decode=True), dict(part.items()))
    return parts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("wav", type=Path)
    parser.add_argument("--post", metavar="URL", help="e.g. http://localhost:8000")
    parser.add_argument("--device-id", default=PLACEHOLDER_DEVICE)
    parser.add_argument("--device-key", help="X-Device-Key for --post")
    args = parser.parse_args()

    audio, sr = sf.read(args.wav, dtype="float32")
    assert sr == 16000 and audio.ndim == 1, "expected mono 16 kHz WAV"
    reference = reference_rois(audio.copy(), sr)

    failures: list[str] = []

    def check(ok: bool, message: str) -> None:
        print(("  ok   " if ok else "  FAIL ") + message)
        if not ok:
            failures.append(message)

    bodies: list[tuple[str, bytes]] = []

    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        exe = work / "upload_body_harness.exe"
        sources = [str(HERE / "upload_body_harness.cpp")] + [
            str(p)
            for sub in ("dsp", "upload")
            for p in sorted((FIRMWARE / "src" / sub).glob("*.cpp"))
        ]
        # -static: on this Windows machine the antivirus blocks the
        # dynamically linked build of this harness from being written.
        subprocess.run(
            ["g++", "-std=c++17", "-O2", "-static", "-Wall", "-Wextra",
             "-I", str(FIRMWARE / "include"), "-I", str(FIRMWARE / "src"),
             *sources, "-o", str(exe)],
            check=True,
        )
        unix_ms = int(time.time() * 1000)
        output = subprocess.run(
            [str(exe), args.device_id, str(unix_ms)],
            input=audio.tobytes(), check=True, capture_output=True,
        ).stdout

    # Split "BODY <boundary> <length>\n<body>" frames; each body ends
    # with its closing "--<boundary>--" delimiter.
    frames: list[tuple[str, int, bytes]] = []
    pos = 0
    while pos < len(output):
        newline = output.index(b"\n", pos)
        _, boundary, counted = output[pos:newline].decode().split()
        closing = f"\r\n--{boundary}--\r\n".encode()
        end = output.index(closing, newline) + len(closing)
        frames.append((boundary, int(counted), output[newline + 1:end]))
        pos = end

    check(len(frames) == len(reference),
          f"roi count {len(frames)} vs reference {len(reference)}")

    for i, (boundary, counted, body) in enumerate(frames):
        print(f"roi {i}:")
        check(counted == len(body),
              f"content-length {counted} == bytes written {len(body)}")

        parts = parse_multipart(body, boundary)
        check(list(parts) == EXPECTED_FIELDS, "form fields and order")

        text = {k: v[0].decode() for k, v in parts.items() if k != "audio_file"}
        meta_raw = text["edge_processing_metadata"]
        meta = json.loads(meta_raw)
        check(isinstance(meta, dict)
              and len(meta_raw.encode()) <= settings.max_edge_metadata_size_bytes,
              f"metadata is a JSON object, {len(meta_raw)} bytes")

        try:
            validated = RecordingUploadMetadata(
                client_upload_id=text["client_upload_id"],
                capture_session_id=text["capture_session_id"],
                snippet_sequence=text["snippet_sequence"],
                capture_started_at=text["capture_started_at"],
                roi_start_seconds=text["roi_start_seconds"],
                roi_end_seconds=text["roi_end_seconds"],
                edge_processing_version=text["edge_processing_version"],
                edge_processing_metadata=meta,
            )
        except Exception as error:  # noqa: BLE001
            check(False, f"backend schema rejected fields: {error}")
            continue
        check(True, "backend schema accepts fields "
                    f"({validated.roi_start_seconds:.3f}-{validated.roi_end_seconds:.3f} s, "
                    f"{validated.capture_started_at.isoformat()})")

        wav_bytes, headers = parts["audio_file"]
        check(headers.get("Content-Type") == "audio/wav", "audio part content type")
        info = sf.info(io.BytesIO(wav_bytes))
        check(info.format == "WAV" and info.subtype == "PCM_16"
              and info.channels == 1 and info.samplerate == 16000,
              f"WAV {info.format}/{info.subtype}, {info.channels} ch, {info.samplerate} Hz")

        duration = info.frames / info.samplerate
        gap = abs(duration - validated.roi_duration_seconds)
        check(gap <= settings.roi_duration_tolerance_seconds,
              f"WAV {duration:.4f} s vs interval {validated.roi_duration_seconds:.4f} s")

        samples, _ = sf.read(io.BytesIO(wav_bytes), dtype="float64")
        if i < len(reference) and len(samples) == len(reference[i]):
            err = float(np.max(np.abs(samples - reference[i])))
            check(err <= 2 / 32768,
                  f"samples vs Python reference, max error {err * 32768:.2f} LSB")
        else:
            check(False, "sample count differs from reference")

        bodies.append((boundary, body))

    if args.post and not failures:
        if args.device_id == PLACEHOLDER_DEVICE:
            print("--post needs --device-id of a registered device")
            return 1
        for i, (boundary, body) in enumerate(bodies):
            request = urllib.request.Request(
                args.post.rstrip("/") + "/api/v1/recordings",
                data=body,
                method="POST",
                headers={
                    "Content-Type": f"multipart/form-data; boundary={boundary}",
                    **({"X-Device-Key": args.device_key} if args.device_key else {}),
                },
            )
            try:
                with urllib.request.urlopen(request) as response:
                    print(f"POST roi {i}: {response.status} {response.read()[:300]!r}")
            except urllib.error.HTTPError as error:
                print(f"POST roi {i}: {error.code} {error.read()[:500]!r}")
                failures.append(f"POST roi {i}")

    print("PASS" if not failures else f"{len(failures)} check(s) failed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
