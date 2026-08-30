"""Headless capture from a Cynthion running the USB Analyzer gateware.

Packetry has no CLI capture mode, so this drives the analyzer directly and
writes a pcap that Packetry can open. Everything here is read off the gateware
source in `cynthion.gateware.analyzer` (top.py, analyzer.py, fifo.py, events.py),
not guessed.

Control plane, all vendor requests to interface 0:

    SET_STATE  bmRequestType 0x41, bRequest 1, wValue = state byte
    GET_STATE  bmRequestType 0xC1, bRequest 0, 1 byte in
    GET_SPEEDS bmRequestType 0xC1, bRequest 2, 1 byte in

State byte: bit 0 enables capture, bits 1-2 select speed. Bits 3-7 control VBUS
routing and are deliberately left at zero, which keeps the default TARGET-C to
TARGET-A passthrough. Never set them here: toggling VBUS power-cycles the device
under test.

Data plane, bulk IN endpoint 0x81, big-endian throughout:

    event   0xFF, code, timestamp:u16
    packet  length:u16, timestamp:u16, then `length` bytes (PID, payload, CRC16)

A length can never begin with 0xFF because the maximum is 1027, so the marker is
unambiguous.
"""

from __future__ import annotations

import struct
import time
from collections.abc import Iterator
from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path

VENDOR_ID = 0x1D50
PRODUCT_ID = 0x615B

INTERFACE = 0
BULK_ENDPOINT = 0x81
MAX_BULK_PACKET_SIZE = 512

REQ_GET_STATE = 0
REQ_SET_STATE = 1
REQ_GET_SPEEDS = 2
REQ_GET_MINOR_VERSION = 4

TYPE_VENDOR_INTERFACE_OUT = 0x41
TYPE_VENDOR_INTERFACE_IN = 0xC1

STATE_ENABLE = 1 << 0

LINKTYPE_USB_2_0 = 288

MAX_PACKET_SIZE = 1024 + 1 + 2
"""Maximum payload, plus a 1-byte PID and a 2-byte CRC16."""

CLOCK_HZ = 60_000_000
"""ULPI clock. The 16-bit timestamp counts these, so it wraps every ~1.09 ms."""


class StreamDesyncError(RuntimeError):
    """The byte stream no longer parses; continuing would produce garbage."""


class Speed(IntEnum):
    """Bits 1-2 of the state byte."""

    HIGH = 0b00
    FULL = 0b01
    LOW = 0b10
    AUTO = 0b11


class Event(IntEnum):
    NONE = 0
    CAPTURE_STOP_NORMAL = 1
    CAPTURE_STOP_FULL = 2
    CAPTURE_STOP_ERROR = 3
    CAPTURE_START_HIGH = 4
    CAPTURE_START_FULL = 5
    CAPTURE_START_LOW = 6
    CAPTURE_START_AUTO = 7
    SPEED_DETECT_HIGH = 8
    SPEED_DETECT_FULL = 9
    SPEED_DETECT_LOW = 10
    SPEED_DETECT_AUTO = 11
    LINESTATE_SE0 = 12
    LINESTATE_CHIRP_J = 13
    LINESTATE_CHIRP_K = 14
    LINESTATE_CHIRP_SE1 = 15
    LINESTATE_LS_J = 16
    LINESTATE_LS_K = 17
    LINESTATE_FS_J = 18
    LINESTATE_FS_K = 19
    LINESTATE_SE1 = 20
    VBUS_INVALID = 21
    VBUS_VALID = 22
    LS_ATTACH = 23
    FS_ATTACH = 24
    BUS_RESET = 25
    DEVICE_CHIRP_VALID = 26
    HOST_CHIRP_VALID = 27
    SUSPEND = 28
    RESUME = 29
    LS_KEEPALIVE = 30


@dataclass(frozen=True)
class CapturedPacket:
    timestamp: int
    """Accumulated clock cycles since capture start."""
    data: bytes


@dataclass(frozen=True)
class CapturedEvent:
    timestamp: int
    code: int

    @property
    def name(self) -> str:
        try:
            return Event(self.code).name
        except ValueError:
            return f"UNKNOWN_{self.code}"


class StreamDecoder:
    """Turns the analyzer's byte stream into packets and events.

    Fed incrementally; holds partial records between feeds. The 16-bit timestamp
    is extended by counting wraps, which is exact only while records arrive more
    often than the ~1.09 ms wrap period. Ordering is always exact; absolute times
    on an idle bus are not.
    """

    def __init__(self) -> None:
        self._buffer = bytearray()
        self._epoch = 0
        self._last_raw = 0

    def _extend(self, raw: int) -> int:
        if raw < self._last_raw:
            self._epoch += 1 << 16
        self._last_raw = raw
        return self._epoch + raw

    def feed(self, chunk: bytes) -> Iterator[CapturedPacket | CapturedEvent]:
        self._buffer.extend(chunk)
        while True:
            if len(self._buffer) < 4:
                return
            if self._buffer[0] == 0xFF:
                code = self._buffer[1]
                raw = struct.unpack_from(">H", self._buffer, 2)[0]
                del self._buffer[:4]
                yield CapturedEvent(self._extend(raw), code)
                continue
            length, raw = struct.unpack_from(">HH", self._buffer, 0)
            if length > MAX_PACKET_SIZE:
                raise StreamDesyncError(
                    f"implausible packet length {length}; stream is out of step"
                )
            # The gateware's ring buffer is 16-bit words, so every record is
            # word-aligned: an odd-length packet is followed by one padding byte.
            padded = length + (length & 1)
            if len(self._buffer) < 4 + padded:
                return
            data = bytes(self._buffer[4 : 4 + length])
            del self._buffer[: 4 + padded]
            yield CapturedPacket(self._extend(raw), data)


class PcapWriter:
    """Classic pcap, LINKTYPE_USB_2_0, so Packetry and Wireshark can read it."""

    def __init__(self, path: Path, start_time: float) -> None:
        self._file = path.open("wb")
        self._start = start_time
        self._file.write(struct.pack("<IHHiIII", 0xA1B2C3D4, 2, 4, 0, 0, 65535, LINKTYPE_USB_2_0))

    def write(self, packet: CapturedPacket) -> None:
        when = self._start + packet.timestamp / CLOCK_HZ
        seconds = int(when)
        micros = int((when - seconds) * 1_000_000)
        self._file.write(struct.pack("<IIII", seconds, micros, len(packet.data), len(packet.data)))
        self._file.write(packet.data)

    def close(self) -> None:
        self._file.close()

    def __enter__(self) -> PcapWriter:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


TRANSFER_COUNT = 8
TRANSFER_SIZE = 64 * 1024


def capture(
    path: Path,
    speed: Speed = Speed.AUTO,
    duration: float | None = None,
    on_event: object = None,
) -> tuple[int, int]:
    """Capture to `path` until `duration` elapses or Ctrl-C. Returns (packets, events).

    Uses a pool of asynchronous transfers rather than synchronous reads. A
    synchronous ``bulkRead`` that times out raises before returning the bytes it
    already received, so on a bursty bus it silently discards data. For a capture
    tool that is a correctness bug, not a performance one.
    """
    import usb1

    decoder = StreamDecoder()
    counts = {"packets": 0, "events": 0}
    failure: list[BaseException] = []

    with usb1.USBContext() as context:
        handle = context.openByVendorIDAndProductID(VENDOR_ID, PRODUCT_ID)
        if handle is None:
            raise RuntimeError(
                f"No Cynthion analyzer found ({VENDOR_ID:04x}:{PRODUCT_ID:04x}). "
                "Check it is connected and running the USB Analyzer gateware."
            )
        try:
            handle.claimInterface(INTERFACE)
        except usb1.USBError as exc:
            # macOS reports a claimed interface as ACCESS rather than BUSY.
            raise RuntimeError(
                f"Cannot claim the analyzer interface ({exc}). Packetry holds it exclusively "
                "while open; quit Packetry and retry."
            ) from exc

        # Always disable first. The gateware's OVERRUN state only clears when the
        # host stops capture, so re-enabling on top of a previous crashed run is a
        # silent no-op that yields an empty capture.
        handle.controlWrite(TYPE_VENDOR_INTERFACE_OUT, REQ_SET_STATE, 0, INTERFACE, b"")
        state = STATE_ENABLE | (int(speed) << 1)
        handle.controlWrite(TYPE_VENDOR_INTERFACE_OUT, REQ_SET_STATE, state, INTERFACE, b"")
        started = time.time()
        running = True

        try:
            with PcapWriter(path, started) as writer:

                def on_transfer(transfer: object) -> None:
                    status = transfer.getStatus()
                    if status not in (usb1.TRANSFER_COMPLETED, usb1.TRANSFER_TIMED_OUT):
                        return
                    for record in decoder.feed(transfer.getBuffer()[: transfer.getActualLength()]):
                        if isinstance(record, CapturedPacket):
                            writer.write(record)
                            counts["packets"] += 1
                        else:
                            counts["events"] += 1
                            if on_event is not None:
                                on_event(record)
                    if running:
                        try:
                            transfer.submit()
                        except usb1.USBError as exc:  # device unplugged mid-capture
                            failure.append(exc)

                transfers = []
                for _ in range(TRANSFER_COUNT):
                    transfer = handle.getTransfer()
                    transfer.setBulk(BULK_ENDPOINT, TRANSFER_SIZE, callback=on_transfer)
                    transfer.submit()
                    transfers.append(transfer)

                try:
                    while duration is None or time.time() - started < duration:
                        context.handleEventsTimeout(0.1)
                        if failure:
                            break
                except KeyboardInterrupt:
                    pass

                running = False
                for transfer in transfers:
                    if transfer.isSubmitted():
                        transfer.cancel()
                deadline = time.time() + 1.0
                while any(t.isSubmitted() for t in transfers) and time.time() < deadline:
                    context.handleEventsTimeout(0.05)
        finally:
            # Always stop the analyzer, even on error, so it is not left capturing.
            handle.controlWrite(TYPE_VENDOR_INTERFACE_OUT, REQ_SET_STATE, 0, INTERFACE, b"")
            handle.releaseInterface(INTERFACE)
            handle.close()

    if failure:
        raise failure[0]
    return counts["packets"], counts["events"]
