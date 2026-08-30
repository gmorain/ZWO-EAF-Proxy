"""ZWO EAF protocol model.

Every constant here is read off a capture in `docs/protocol/`, never guessed.
"""

from __future__ import annotations

ZWO_VID = 0x03C3
"""ZWO's USB vendor ID."""

ZWO_EAF_PID = 0x1F10
"""Confirmed from `captures/01-enumerate.pcap`."""

MAGIC = b"\x7e\x5a"
"""Leads every report body, both directions."""

REPORT_IN = 1
"""Report ID the device answers on, via GET_REPORT feature wValue 0x0301."""

REPORT_OUT = 3
"""Report ID the host commands on, via SET_REPORT feature wValue 0x0303."""

REPORT_SIZE = 16
"""Report ID plus 15 payload bytes. The host asks for 17 on reads and gets 16."""

BODY_SIZE = 12
"""Payload after `<report id> 7E 5A <register>`."""

TEMPERATURE_BIAS = 30000
"""Subtract, then divide by 100, for degrees Celsius. The device sends this
constant back at body bytes 10..11 of register 0x03."""

TEMPERATURE_SCALE = 100


class Register:
    """Registers seen on the wire. Anything absent here was never observed."""

    READ = 0x02
    """Read accessor. Its first argument names the register to read."""

    STATE = 0x03
    """Moving flag, position, temperature. Read/write."""

    IDENTITY = 0x04
    """Firmware triplet and model string. Read only."""

    SERIAL = 0x0C
    """Eight bytes. Read only, and slow: the real device NAKed 37-51 polls."""

    UNKNOWN_0D = 0x0D
    """Answers with valid framing and a zero body. Meaning unknown."""


FIRMWARE_VERSION = (3, 8, 2)
"""What the captured unit reported. The ASIAIR compares this against the release
it knows about: match it to stay quiet, or set it lower to make the ASIAIR offer
an upgrade, which is the only known route to capturing the update protocol."""

IDENTITY_MODEL = bytes.fromhex("454541464e")
"""Byte 3 (0x45) is unexplained and reproduced verbatim, then ASCII `EAFN`.
Confirmed against the ASIAIR's own screen."""

PLACEHOLDER_SERIAL = bytes.fromhex("6000000000000000")
"""Register 0x0C is 0x6000 followed by the ESP32's MAC. A real unit's value
identifies that unit, so it is configurable and never committed."""

USB_SERIAL_STRING = "123456"
"""The USB string descriptor, which is a literal placeholder on real hardware
and unrelated to the serial reported by register 0x0C."""
