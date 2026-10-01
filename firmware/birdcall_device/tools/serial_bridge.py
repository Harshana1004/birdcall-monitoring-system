"""
Serial bridge: stands in for the A7670 modem during development.

Relays ROI uploads from the device to the backend and supplies
wall-clock time (see src/bridge/serial_bridge.h for the protocol).
Everything else the device prints is echoed, except the level-meter
lines (use --meter to show them).

Close the PlatformIO serial monitor first -- the port can only be
open once. Needs pyserial; PlatformIO's Python has it:

    ~/.platformio/penv/Scripts/python tools/serial_bridge.py --port COM4

In continuous mode (the default at boot, with UPLOAD_VIA_MODEM =
false in config.h) the device uploads ROIs on its own as it detects
them; just leave the bridge running. In bench mode (send b within 3 s
of boot) type u + Enter to record 10 s and upload its ROIs, or use
--upload to trigger one capture straight away. Ctrl+C to quit.
"""

from __future__ import annotations

import argparse
import base64
import queue
import re
import sys
import threading
import time
import urllib.error
import urllib.request

import serial

# One line of an upload body: base64, 4-char groups, padding only at
# the end (the device writes 76-char lines, the last may be shorter).
BASE64_LINE = re.compile(r"(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?")


def post_body(backend: str, boundary: str, body: bytes) -> tuple[int, str]:
    request = urllib.request.Request(
        backend.rstrip("/") + "/api/v1/recordings",
        data=body,
        method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, response.read().decode(errors="replace")
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode(errors="replace")
    except OSError as error:
        return 0, str(error)


def send_time(port: serial.Serial) -> None:
    port.write(f"t{int(time.time() * 1000)}\n".encode())


def keyboard_reader(commands: queue.Queue[str]) -> None:
    for line in sys.stdin:
        commands.put(line.strip())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--backend", default="http://127.0.0.1:8000")
    parser.add_argument("--upload", action="store_true",
                        help="trigger one capture + upload on connect")
    parser.add_argument("--meter", action="store_true",
                        help="also print the level-meter lines")
    args = parser.parse_args()

    port = serial.Serial()
    port.port = args.port
    port.baudrate = args.baud
    port.timeout = 0.5
    # Don't pulse DTR/RTS -- on the DevKitC they reset the chip.
    port.dtr = False
    port.rts = False
    port.open()

    print(f"bridge: {args.port} <-> {args.backend}  (u = capture + upload, "
          "d/r = other device commands, Ctrl+C = quit)")
    send_time(port)
    if args.upload:
        port.write(b"u")

    commands: queue.Queue[str] = queue.Queue()
    threading.Thread(target=keyboard_reader, args=(commands,), daemon=True).start()

    upload: dict | None = None

    try:
        while True:
            while not commands.empty():
                command = commands.get()
                if command:
                    port.write(command[0].encode())

            raw = port.readline()
            if not raw:
                continue
            line = raw.decode(errors="replace").rstrip("\r\n")

            if upload is not None:
                if line == "UPLOAD_END":
                    body = b"".join(upload["chunks"])
                    if len(body) != upload["length"]:
                        print(f"bridge: roi {upload['seq']} body is {len(body)} bytes, "
                              f"expected {upload['length']} -- reporting failure")
                        status, detail = 0, "incomplete body"
                    else:
                        status, detail = post_body(args.backend, upload["boundary"], body)
                    print(f"bridge: roi {upload['seq']} POST -> {status} "
                          f"({len(body)} bytes, {time.monotonic() - upload['t0']:.1f} s) "
                          f"{detail[:160]}")
                    port.write(f"UPLOAD_RESULT {status}\n".encode())
                    upload = None
                elif BASE64_LINE.fullmatch(line):
                    upload["chunks"].append(base64.b64decode(line))
                else:
                    # In continuous mode other tasks may log between the
                    # body's lines (always as whole lines).
                    print(f"device: {line}")
                continue

            if line.startswith("UPLOAD_BEGIN "):
                _, seq, boundary, length = line.split()
                upload = {"seq": seq, "boundary": boundary, "length": int(length),
                          "chunks": [], "t0": time.monotonic()}
                print(f"bridge: receiving roi {seq} ({int(length)} bytes)...")
            elif line == "TIME_REQUEST":
                send_time(port)
            elif line.startswith("rms ") and not args.meter:
                pass
            else:
                print(f"device: {line}")
    except KeyboardInterrupt:
        pass
    finally:
        port.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
