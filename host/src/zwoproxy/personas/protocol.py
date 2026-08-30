"""Encode and decode EAF reports.

Layout and field meanings come from `docs/protocol/registers.md`. This module is
pure: it does no I/O, so it can be tested against bytes taken from the captures.
"""

from __future__ import annotations

from dataclasses import dataclass

from .eaf import (
    BODY_SIZE,
    FIRMWARE_VERSION,
    IDENTITY_MODEL,
    MAGIC,
    REPORT_IN,
    REPORT_OUT,
    REPORT_SIZE,
    TEMPERATURE_BIAS,
    TEMPERATURE_SCALE,
    Register,
)

SETTINGS_BASE = 0x01
"""Body byte 9 of register 0x03, bit 0. Set in every capture, meaning unknown."""

SETTINGS_REVERSE = 0x02
"""Body byte 9, bit 1: the ASIAIR's focuser Reverse toggle.

The host writes it, the device stores it, and every state reply echoes it back.
See `captures/18-reverse.pcap` and docs/protocol/registers.md.
"""


class MalformedReport(ValueError):
    """The host sent something that is not a report this device understands."""


@dataclass(frozen=True)
class ReadRegister:
    """`7E 5A 02 <register>`: read the named register."""

    register: int


@dataclass(frozen=True)
class WriteState:
    """`7E 5A 03 <body>`: move, halt, or set the current position.

    With `go` set, `position` is an absolute target. With `go` clear, `sync`
    decides: set it and the device is redefined to be at `position` without
    moving, clear it and the device halts and ignores `position`.
    """

    go: bool
    position: int
    sync: bool = False
    settings: int | None = None
    """Body byte 9, or None when the report was too short to carry it."""


Command = ReadRegister | WriteState


def parse_command(data: bytes) -> Command:
    """Decode one SET_REPORT payload.

    Trailing bytes past the arguments a command defines are ignored: the ASIAIR
    leaks uninitialised heap into the padding, so they are not reliably zero.
    """
    if len(data) < 5:
        raise MalformedReport(f"report too short: {len(data)} bytes")
    if data[0] != REPORT_OUT:
        raise MalformedReport(f"unexpected report id {data[0]:#04x}")
    if data[1:3] != MAGIC:
        raise MalformedReport(f"bad magic {data[1:3].hex()}")

    register = data[3]
    if register == Register.READ:
        return ReadRegister(register=data[4])
    if register == Register.STATE:
        body = data[4 : 4 + BODY_SIZE]
        if len(body) < 6:
            raise MalformedReport("state write truncated before the position")
        return WriteState(
            go=bool(body[0]),
            position=int.from_bytes(body[2:6], "big"),
            sync=len(body) > 6 and bool(body[6]),
            settings=body[9] if len(body) > 9 else None,
        )
    raise MalformedReport(f"write to unhandled register {register:#04x}")


def frame_reply(register: int, body: bytes) -> bytes:
    """Wrap a 12-byte body as a report the host can read back."""
    if len(body) != BODY_SIZE:
        raise ValueError(f"body must be {BODY_SIZE} bytes, got {len(body)}")
    reply = bytes([REPORT_IN]) + MAGIC + bytes([register]) + body
    assert len(reply) == REPORT_SIZE
    return reply


def encode_temperature(celsius: float) -> int:
    """Degrees to the raw u16. Clamped, since the field cannot express more."""
    raw = round(celsius * TEMPERATURE_SCALE) + TEMPERATURE_BIAS
    return max(0, min(0xFFFF, raw))


def decode_temperature(raw: int) -> float:
    return (raw - TEMPERATURE_BIAS) / TEMPERATURE_SCALE


def encode_state(
    *, moving: bool, position: int, celsius: float, settings: int = SETTINGS_BASE
) -> bytes:
    """The register 0x03 body.

    `settings` is byte 9, which the host owns and the device only stores. Echo
    back whatever was last written rather than a constant, or the ASIAIR's
    Reverse toggle never appears to take.
    """
    if not 0 <= position <= 0xFFFFFFFF:
        raise ValueError(f"position out of range: {position}")
    return (
        bytes([1 if moving else 0, 0])
        + position.to_bytes(4, "big")
        + bytes([0])
        + encode_temperature(celsius).to_bytes(2, "big")
        + bytes([settings & 0xFF])
        + TEMPERATURE_BIAS.to_bytes(2, "big")
    )


def identity_body(version: tuple[int, int, int] = FIRMWARE_VERSION) -> bytes:
    """Version triplet then the model, zero padded to a body."""
    if not all(0 <= part <= 0xFF for part in version):
        raise ValueError(f"version parts must be bytes: {version}")
    return (bytes(version) + IDENTITY_MODEL).ljust(BODY_SIZE, b"\x00")


def serial_body(serial: bytes) -> bytes:
    """Register 0x0C: eight bytes, zero padded to the body length."""
    if len(serial) > BODY_SIZE:
        raise ValueError(f"serial longer than a body: {len(serial)} bytes")
    return serial.ljust(BODY_SIZE, b"\x00")


def zero_body() -> bytes:
    return bytes(BODY_SIZE)
