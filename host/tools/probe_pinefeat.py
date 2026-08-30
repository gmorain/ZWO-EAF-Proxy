#!/usr/bin/env python3
"""Pinefeat CEF bench tool: talk to the controller over USB CDC, with no board.

The CEF has no halt command. The proposed pseudo-halt is to read position with
`f` and immediately write `m<that position>`. That only works if the controller
accepts a retarget mid-move, which is what this measures.

A real EAF overshoots its own halt by up to 353 steps and the ASIAIR accepts it
(docs/protocol/pinefeat.md). The pseudo-halt only has to land in that envelope.

Every finding in docs/protocol/pinefeat.md came from this. It drives the codec in
`zwoproxy.backends.pinefeat`, so it exercises the shipped parser rather than a
private copy of the protocol.

    cd host
    uv run python tools/probe_pinefeat.py                    # identify, no movement
    uv run python tools/probe_pinefeat.py --send "v,r,a,f"   # arbitrary commands
    uv run python tools/probe_pinefeat.py --test             # the retarget test

Nothing moves without --test or an explicit move in --send. `tools/fake_cef.py`
runs the same probe against a simulated controller on a pty, so it can be changed
with no hardware attached.
"""

from __future__ import annotations

import argparse
import glob
import os
import select
import sys
import termios
import time
import tty
from dataclasses import dataclass
from math import log2

from zwoproxy.backends import pinefeat

TIMEOUT = 2.0
ENVELOPE = 353  # steps; the real EAF's worst observed halt overshoot


class Port:
    """A line-oriented ASCII link over a CDC-ACM tty. Stdlib only."""

    trace = False

    def __init__(self, path: str, baud: int = 115200) -> None:
        # cu.* rather than tty.*: it does not block waiting for carrier detect.
        self.fd = os.open(path, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        os.set_blocking(self.fd, True)
        tty.setraw(self.fd, termios.TCSANOW)
        attrs = termios.tcgetattr(self.fd)
        speed = getattr(termios, f"B{baud}")
        attrs[4] = attrs[5] = speed
        termios.tcsetattr(self.fd, termios.TCSANOW, attrs)
        termios.tcflush(self.fd, termios.TCIOFLUSH)
        self.path = path

    def close(self) -> None:
        os.close(self.fd)

    def _read_line(self, timeout: float = TIMEOUT) -> bytes:
        deadline = time.monotonic() + timeout
        buf = bytearray()
        while time.monotonic() < deadline:
            ready, _, _ = select.select([self.fd], [], [], deadline - time.monotonic())
            if not ready:
                continue
            chunk = os.read(self.fd, 64)
            if not chunk:
                continue
            buf += chunk
            if b"\n" in buf:
                return bytes(buf)
        raise TimeoutError(f"no reply within {timeout}s, got {bytes(buf)!r}")

    def ask(self, command: str, timeout: float = TIMEOUT) -> str:
        os.write(self.fd, pinefeat.frame(command))
        reply = pinefeat.unframe(self._read_line(timeout))
        if self.trace:
            print(f"    -> {command!r:12} <- {reply!r}", file=sys.stderr)
        return reply


def find_port(explicit: str | None) -> str:
    if explicit:
        return explicit
    candidates = sorted(glob.glob("/dev/cu.usbmodem*") + glob.glob("/dev/cu.usbserial*"))
    if not candidates:
        sys.exit("no /dev/cu.usbmodem* found. Plug the CEF in, or pass --port.")
    if len(candidates) > 1:
        sys.exit(f"several ports, pick one with --port: {candidates}")
    return candidates[0]


@dataclass
class Cycle:
    commanded_at: int
    stopped_at: int

    @property
    def overshoot(self) -> int:
        return self.stopped_at - self.commanded_at


APERTURE_REFERENCE = 5.6
APERTURE_FLOOR, APERTURE_CAP = 1 / 3, 2.0


def default_aperture(f_min: float) -> float:
    """Stop down further on a fast lens than a slow one.

    Aberration severity tracks the cone angle, so a fast lens has more to
    correct and more light to spare. See specs/features/002-pinefeat-cef-backend.md.
    """
    stops = min(APERTURE_CAP, max(APERTURE_FLOOR, log2(APERTURE_REFERENCE / f_min)))
    return f_min * 2 ** (stops / 2)


NO_LENS_DATA = "0-65535"
"""What `r` answers when the controller cannot talk to the lens."""

CALIBRATION_FAILED = "0-0"
"""What `r` answers after a `c` that returned `er`."""


def usable(raw_range: str) -> bool:
    return raw_range not in (NO_LENS_DATA, CALIBRATION_FAILED)


def identify(port: Port) -> tuple[int, int]:
    """Print what the controller says about itself. Returns the position range."""
    version = pinefeat.check(port.ask(pinefeat.GET_VERSION))
    raw_range = pinefeat.check(port.ask(pinefeat.GET_RANGE))
    position = pinefeat.parse_position(port.ask(pinefeat.GET_POSITION))
    moving = pinefeat.parse_is_moving(port.ask(pinefeat.IS_MOVING))
    print(f"port      {port.path}")
    print(f"version   {version}")
    print(f"range     {raw_range}")
    print(f"position  {position}")
    print(f"moving    {'yes' if moving else 'no'}")
    if raw_range == NO_LENS_DATA:
        print("\n  the controller has no lens data. Check the AF/MF switch.")
    elif raw_range == CALIBRATION_FAILED:
        print("\n  calibration failed and the state is sticky. Switch to AF, then re-run.")
    low, _, high = raw_range.partition("-")
    return int(low or 0), int(high)


def settle(port: Port, timeout: float = 30.0) -> int:
    """Wait for movement to finish. Returns the resting position."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not pinefeat.parse_is_moving(port.ask(pinefeat.IS_MOVING)):
            return pinefeat.parse_position(port.ask(pinefeat.GET_POSITION))
        time.sleep(0.05)
    raise TimeoutError("still moving after 30s")


def retarget_cycle(port: Port, *, target: int, delay: float) -> Cycle:
    """Start a long move, let it run, then pseudo-halt it. Returns where it stopped."""
    pinefeat.check(port.ask(pinefeat.move_to(target)))
    time.sleep(delay)
    if not pinefeat.parse_is_moving(port.ask(pinefeat.IS_MOVING)):
        raise RuntimeError(f"move to {target} finished within {delay}s; use a longer --travel")

    # The pseudo-halt, as tight as the link allows: read, then retarget.
    commanded_at = pinefeat.parse_position(port.ask(pinefeat.GET_POSITION))
    pinefeat.check(port.ask(pinefeat.move_to(commanded_at)))
    return Cycle(commanded_at=commanded_at, stopped_at=settle(port))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default=None, help="default: the only /dev/cu.usbmodem*")
    parser.add_argument("--test", action="store_true", help="move the lens and measure")
    parser.add_argument("--cycles", type=int, default=3)
    parser.add_argument("--travel", type=int, default=2000, help="steps to command per cycle")
    parser.add_argument("--delay", type=float, default=0.5, help="seconds into the move")
    parser.add_argument("--trace", action="store_true", help="log every command and reply")
    parser.add_argument("--send", default=None, help="comma-separated commands to run, then exit")
    parser.add_argument("--calibrate", action="store_true", help="send c, report the range")
    parser.add_argument(
        "--vet",
        nargs="?",
        type=int,
        const=3,
        default=None,
        help="calibrate N times and report whether travel is reproducible",
    )
    parser.add_argument("--focus", type=int, default=None, help="move to an absolute position")
    parser.add_argument(
        "--aperture", default=None, help="f-number to set, or 'auto' for the computed default"
    )
    parser.add_argument("--scan", default=None, help="focus sweep, START:STOP:STEP, one session")
    parser.add_argument("--dwell", type=float, default=3.0, help="seconds held at each scan step")
    parser.add_argument("--timeout", type=float, default=TIMEOUT, help="seconds to wait per reply")
    args = parser.parse_args()

    Port.trace = args.trace or args.send is not None
    port = Port(find_port(args.port))
    if args.vet:
        seen = []
        for n in range(args.vet):
            port.ask(pinefeat.CALIBRATE, timeout=60)
            while pinefeat.parse_is_moving(port.ask(pinefeat.IS_MOVING)):
                time.sleep(0.1)
            raw = pinefeat.check(port.ask(pinefeat.GET_RANGE))
            seen.append(int(raw.rsplit("-", 1)[-1]) if usable(raw) else 0)
            print(f"  calibration {n + 1}: {raw}")
        spread = max(seen) - min(seen)
        mean = sum(seen) / len(seen)
        if not all(seen):
            print("\nUNUSABLE: calibration failed. Check the AF/MF switch.")
            return 1
        share = spread / mean
        print(f"\nspread {spread} steps over a mean of {mean:.0f}, {share:.2%}")
        print("USABLE" if share < 0.01 else "UNUSABLE: travel is not reproducible")
        return 0 if share < 0.01 else 1

    if args.calibrate:
        print(f"c -> {port.ask(pinefeat.CALIBRATE, timeout=60)}")
        while pinefeat.parse_is_moving(port.ask(pinefeat.IS_MOVING)):
            time.sleep(0.1)
        print(f"travel {pinefeat.check(port.ask(pinefeat.GET_RANGE))}")

    if args.aperture:
        low = float(pinefeat.check(port.ask(pinefeat.GET_APERTURE_RANGE)).split("-")[0])
        wanted = default_aperture(low) if args.aperture == "auto" else float(args.aperture)
        reply = port.ask(pinefeat.set_aperture(wanted))
        note = f" (default for f/{low:g})" if args.aperture == "auto" else ""
        print(f"aperture f/{wanted:.1f}{note} -> {reply}")

    if args.focus is not None:
        pinefeat.check(port.ask(pinefeat.move_to(args.focus)))
        print(f"focus {settle(port)}   (commanded {args.focus})")

    if args.calibrate or args.aperture or args.focus is not None:
        port.close()
        return 0

    if args.scan:
        # One open port for the whole sweep. Reopening between steps disturbs the
        # controller: see docs/protocol/pinefeat.md.
        first, last, step = (int(v) for v in args.scan.split(":"))
        print(f"scanning {first} to {last} by {step}, {args.dwell}s at each. Ctrl-C to stop.")
        for target in range(first, last + (1 if step > 0 else -1), step):
            pinefeat.check(port.ask(pinefeat.move_to(target)))
            while pinefeat.parse_is_moving(port.ask(pinefeat.IS_MOVING)):
                time.sleep(0.05)
            landed = pinefeat.parse_position(port.ask(pinefeat.GET_POSITION))
            flag = "" if landed == target else f"   (commanded {target})"
            print(f"  {landed}{flag}")
            time.sleep(args.dwell)
        port.close()
        return 0

    if args.send:
        for command in args.send.split(","):
            try:
                port.ask(command.strip(), timeout=args.timeout)
            except TimeoutError as error:
                print(f"    {error}", file=sys.stderr)
        port.close()
        return 0
    try:
        low, high = identify(port)
        if not args.test:
            print("\nidentify only. Re-run with --test to measure the retarget.")
            return 0

        # What the backend's begin() will do: c is the only reliable proof that
        # the lens is drivable. r alone answers from cached data in MF.
        if port.ask(pinefeat.CALIBRATE, timeout=30) != pinefeat.OK:
            print(
                "\ncalibration refused: no usable focuser. Check the AF/MF switch.", file=sys.stderr
            )
            return 1
        raw_range = pinefeat.check(port.ask(pinefeat.GET_RANGE))
        if not usable(raw_range):
            print(f"\ncalibrated, but range is {raw_range}: no usable focuser.", file=sys.stderr)
            return 1
        low, _, high_text = raw_range.partition("-")
        low, high = int(low or 0), int(high_text)
        print(f"calibrated, travel {raw_range}")

        start = settle(port)
        print(
            f"\nretarget test: {args.cycles} cycles, {args.travel} steps, halt at {args.delay}s\n"
        )
        cycles = []
        for n in range(args.cycles):
            # Move away from whichever end we are nearest, and stay inside the range.
            outward = start + args.travel <= high
            target = start + args.travel if outward else max(low, start - args.travel)
            cycle = retarget_cycle(port, target=target, delay=args.delay)
            cycles.append(cycle)
            print(
                f"  cycle {n + 1}  commanded at {cycle.commanded_at:>6}"
                f"  stopped at {cycle.stopped_at:>6}  overshoot {cycle.overshoot:+}"
            )
            pinefeat.check(port.ask(pinefeat.move_to(start)))
            settle(port)

        worst = max(abs(c.overshoot) for c in cycles)
        print(f"\nworst overshoot {worst} steps, envelope {ENVELOPE}")
        if worst <= ENVELOPE:
            print("VIABLE: it accepts a retarget mid-move, inside the EAF's own envelope.")
        else:
            print("OUT OF ENVELOPE: it retargets, but wider than a real EAF. Judgement call.")
        return 0
    except pinefeat.PinefeatError as error:
        print(f"\ncontroller refused: {error}", file=sys.stderr)
        return 1
    except (TimeoutError, RuntimeError) as error:
        print(f"\n{error}", file=sys.stderr)
        return 1
    finally:
        port.close()


if __name__ == "__main__":
    sys.exit(main())
