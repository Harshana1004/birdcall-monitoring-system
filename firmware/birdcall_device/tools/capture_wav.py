"""
Trigger a test capture on the device and save it as a WAV.

Sends 'd' over serial; the firmware records 10 s, streams it as
base64 PCM16, then runs the DSP pipeline on the same samples. The
WAV goes to --out and the device's pipeline output to
<out>.device.txt (read by tools/verify/compare_capture.py).

Close the PlatformIO serial monitor first (the port can only be
open once). Needs pyserial -- PlatformIO's Python has it:

    ~/.platformio/penv/Scripts/python tools/capture_wav.py --port COM4 --out capture.wav
"""

from __future__ import annotations

import argparse
import base64
import time
import wave
from pathlib import Path

import serial


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--out", type=Path, default=Path("capture.wav"))
    args = parser.parse_args()

    port = serial.Serial()
    port.port = args.port
    port.baudrate = args.baud
    port.timeout = 1.0
    # Don't pulse DTR/RTS -- on the DevKitC they reset the chip.
    port.dtr = False
    port.rts = False
    port.open()

    # If opening the port did reset the board, wait for it to boot.
    deadline = time.monotonic() + 4.0
    while time.monotonic() < deadline:
        line = port.readline().decode(errors="replace").strip()
        if "Mic running" in line or line.startswith("rms"):
            break

    port.reset_input_buffer()
    port.write(b"d")
    print("Recording 10 s on the device -- make some noise now...")

    sample_rate = count = None
    chunks: list[bytes] = []
    device_lines: list[str] = []
    in_wav = False

    while True:
        raw = port.readline()
        if not raw:
            continue
        line = raw.decode(errors="replace").strip()

        if line.startswith("BEGIN_WAV"):
            _, sr, n = line.split()
            sample_rate, count = int(sr), int(n)
            in_wav = True
            print(f"Receiving {count} samples (~{count * 2 * 4 // 3 // 11520 + 1} s)...")
        elif line == "END_WAV":
            in_wav = False
        elif in_wav:
            chunks.append(base64.b64decode(line))
        elif line.startswith("Back to level meter"):
            break
        elif line.startswith(("Captured", "status=", "roi ")):
            device_lines.append(line)
            print("device:", line)

    port.close()

    pcm = b"".join(chunks)
    if count is None or len(pcm) != count * 2:
        print(f"Incomplete dump: got {len(pcm)} bytes, expected {count and count * 2}")
        return 1

    with wave.open(str(args.out), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm)

    sidecar = args.out.with_suffix(".device.txt")
    sidecar.write_text("\n".join(device_lines) + "\n")
    print(f"Saved {args.out} and {sidecar}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
