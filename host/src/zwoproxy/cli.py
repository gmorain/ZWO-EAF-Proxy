"""Command-line entry point."""

import argparse
import logging
import sys
from pathlib import Path

from . import capture as capture_mod


def _capture(args: argparse.Namespace) -> int:
    speed = capture_mod.Speed[args.speed.upper()]
    print(f"Capturing to {args.output} at {speed.name} speed. Ctrl-C to stop.", file=sys.stderr)

    def report(event: capture_mod.CapturedEvent) -> None:
        print(f"  event {event.name}", file=sys.stderr)

    packets, events = capture_mod.capture(
        Path(args.output), speed=speed, duration=args.duration, on_event=report
    )
    print(f"{packets} packets, {events} events -> {args.output}", file=sys.stderr)
    return 0 if packets else 1


def _serial(text: str) -> bytes:
    """Parse the register 0x0C value: hex, with or without separators."""
    cleaned = text.replace(":", "").replace("-", "").replace(" ", "")
    try:
        value = bytes.fromhex(cleaned)
    except ValueError as error:
        raise argparse.ArgumentTypeError(f"not hex: {text}") from error
    if len(value) != 8:
        raise argparse.ArgumentTypeError(f"serial must be 8 bytes, got {len(value)}")
    return value


def _version(text: str) -> tuple[int, int, int]:
    """Parse the firmware version the persona reports, e.g. 3.8.2."""
    parts = text.split(".")
    if len(parts) != 3:
        raise argparse.ArgumentTypeError(f"want three parts, got {text!r}")
    try:
        values = tuple(int(p) for p in parts)
    except ValueError as error:
        raise argparse.ArgumentTypeError(f"not numeric: {text!r}") from error
    if not all(0 <= v <= 255 for v in values):
        raise argparse.ArgumentTypeError(f"each part must be 0-255: {text!r}")
    return values  # type: ignore[return-value]


def _persona(args: argparse.Namespace) -> int:
    from .backends.simulated import SimulatedFocuser
    from .personas.eaf_device import EAFDevice

    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)-7s %(name)s %(message)s")
    # facedancer pins its own logger to WARN at import time, so lowering the root
    # logger alone leaves the emulation silent.
    logging.getLogger("facedancer").setLevel(level)
    focuser = SimulatedFocuser(
        position=args.position,
        steps_per_second=args.rate,
        celsius=args.temperature,
    )
    kwargs = {
        "focuser": focuser,
        "fallback_celsius": args.temperature,
    }
    if args.firmware_version is not None:
        kwargs["firmware_version"] = args.firmware_version
    if args.serial is not None:
        kwargs["serial"] = args.serial
    device = EAFDevice(**kwargs)
    print("Presenting a ZWO EAF. Connect the ASIAIR to TARGET-C. Ctrl-C to stop.", file=sys.stderr)
    try:
        # emulate() connects at full speed, which is what the real EAF runs at.
        device.emulate()
    except KeyboardInterrupt:
        print("stopped", file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="zwoproxy", description=__doc__)
    sub = parser.add_subparsers(dest="command")

    cap = sub.add_parser("capture", help="capture USB traffic via Cynthion to a pcap")
    cap.add_argument("-o", "--output", default="capture.pcap")
    cap.add_argument("-s", "--speed", default="auto", choices=["auto", "high", "full", "low"])
    cap.add_argument("-d", "--duration", type=float, default=None, help="seconds; omit for Ctrl-C")
    cap.set_defaults(func=_capture)

    per = sub.add_parser("persona", help="present as a ZWO EAF via Facedancer")
    per.add_argument(
        "--serial",
        type=_serial,
        default=None,
        help="register 0x0C, 8 bytes of hex; defaults to a placeholder",
    )
    per.add_argument("--position", type=int, default=0, help="starting step count")
    per.add_argument("--rate", type=float, default=500.0, help="simulated steps per second")
    per.add_argument("--temperature", type=float, default=20.0, help="degrees Celsius to report")
    per.add_argument(
        "--firmware-version",
        type=_version,
        default=None,
        help="version reported by register 0x04, e.g. 3.8.2. Lower than the "
        "real release makes the ASIAIR offer an upgrade",
    )
    per.add_argument("-v", "--verbose", action="store_true")
    per.set_defaults(func=_persona)

    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 1
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
