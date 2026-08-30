"""A fake CEF controller on a pty, to exercise probe_pinefeat.py with no hardware.

    cd host
    uv run python tools/fake_cef.py --test                     # accepts a retarget
    uv run python tools/fake_cef.py --test --refuse-retarget    # and the failing case

Arguments after the flags above are passed through to the probe.
"""

import os
import pty
import re
import subprocess
import sys
import threading
import time

RATE = 1000.0  # steps per second
APERTURE_MIN, APERTURE_MAX = 2.8, 22.6


class Controller:
    def __init__(self) -> None:
        self.position = 1000.0
        self.target = 1000
        self.last = time.monotonic()
        self.accepts_retarget = "--refuse-retarget" not in sys.argv
        self.has_lens = "--no-lens" not in sys.argv  # as if the lens were in MF

    def advance(self) -> None:
        now = time.monotonic()
        elapsed, self.last = now - self.last, now
        remaining = self.target - self.position
        if remaining == 0:
            return
        step = RATE * elapsed
        if abs(remaining) <= step:
            self.position = float(self.target)
        else:
            self.position += step if remaining > 0 else -step

    def reply(self, command: str) -> str:
        self.advance()
        if command == "c":
            return "ok" if self.has_lens else "er"
        if command == "v":
            return "CEF fake 1.0"
        if command == "a":
            return f"{APERTURE_MIN}-{APERTURE_MAX}"
        if match := re.fullmatch(r"a([0-9.]+)", command):
            wanted = float(match.group(1))
            return "ok" if APERTURE_MIN <= wanted <= APERTURE_MAX else "er"
        if command == "r":
            return "0-9999" if self.has_lens else "0-65535"
        if command == "f":
            return str(int(self.position))
        if command == "e":
            return "y" if int(self.position) != self.target else "n"
        if match := re.fullmatch(r"m(\d+)", command):
            moving = int(self.position) != self.target
            if moving and not self.accepts_retarget:
                return "er"  # the dealbreaker case: no retarget mid-move
            self.target = int(match.group(1))
            return "ok"
        return "er"


def serve(master: int, controller: Controller) -> None:
    buf = bytearray()
    while True:
        try:
            chunk = os.read(master, 64)
        except OSError:
            return
        if not chunk:
            return
        buf += chunk
        while b"\n" in buf:
            line, _, rest = buf.partition(b"\n")
            buf = bytearray(rest)
            answer = controller.reply(line.decode().strip())
            os.write(master, (answer + "\n").encode())


master, slave = pty.openpty()
threading.Thread(target=serve, args=(master, Controller()), daemon=True).start()
probe = os.path.join(os.path.dirname(os.path.abspath(__file__)), "probe_pinefeat.py")
skip = {"--refuse-retarget", "--no-lens"}
passthrough = [a for a in sys.argv[1:] if a not in skip]
sys.exit(subprocess.call([sys.executable, probe, "--port", os.ttyname(slave), *passthrough]))
