"""Descriptor bytes the real EAF presents, lifted from `captures/01-enumerate.pcap`.

These are the reference the persona is checked against. Do not edit them to make
a test pass; the capture is the authority.
"""

from __future__ import annotations

DEVICE = bytes.fromhex("1201000200000040c303101f000101020301")
"""18 bytes. bcdUSB 0x0200, class 0/0/0, EP0 64, VID 0x03C3, PID 0x1F10,
bcdDevice 0x0100, strings 1/2/3, one configuration."""

CONFIGURATION = bytes.fromhex(
    "09022200010100a032"  # config: 34 total, 1 interface, 0xA0, 50 (100 mA)
    "090400000103000000"  # interface 0, 1 endpoint, HID, subclass 0, protocol 0
    "092111010001224400"  # HID 1.11, one report descriptor, 68 bytes
    "0705810310000a"  # EP 0x81 IN interrupt, 16 bytes, bInterval 10
)
"""34 bytes."""

REPORT = bytes.fromhex(
    "0600ff"  # Usage Page (Vendor 0xFF00)
    "0901"  # Usage 1
    "a101"  # Collection (Application)
    "8501950f750826ff00150009018102"  # Report 1: Input,  15 bytes
    "8502950f750826ff00150009018102"  # Report 2: Input,  15 bytes
    "8503950f750826ff00150009019102"  # Report 3: Output, 15 bytes
    "8504950f750826ff00150009019102"  # Report 4: Output, 15 bytes
    "c0"  # End Collection
)
"""68 bytes."""

STRINGS = {
    0: bytes.fromhex("04030904"),
    1: bytes.fromhex("08035a0057004f00"),
    2: bytes.fromhex("16035a0057004f002000440065007600690063006500"),
    3: bytes.fromhex("0e03310032003300340035003600"),
}
"""LANGID 0x0409 only, then `ZWO`, `ZWO Device`, `123456`."""
