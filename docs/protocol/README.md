# EAF protocol notes

One file per confirmed finding. Record the capture or artefact it came from, not
just the conclusion, so a wrong reading can be traced back.

## Established

| Fact | Confidence | Source |
|---|---|---|
| VID `0x03C3`, PID `0x1F10` | confirmed | [enumeration.md](enumeration.md) |
| Transport is **USB HID**, vendor usage page | confirmed | [enumeration.md](enumeration.md) |
| Protocol rides **control transfers**, not the interrupt endpoint | confirmed | [enumeration.md](enumeration.md) |
| Report descriptor: 4 reports, 15 bytes each | confirmed | [enumeration.md](enumeration.md) |
| Command magic `7E 5A` | confirmed | [enumeration.md](enumeration.md) |
| Strings `ZWO` / `ZWO Device` / `123456` | confirmed | [enumeration.md](enumeration.md) |
| **The EAF is ESP32-based**: `0x303A:0x1001` ROM identity, then re-enumerates as ZWO | confirmed, 3 observations; nothing enumerates with TARGET-A empty | [enumeration.md](enumeration.md) |
| Move is **absolute**: `0x03` write, `b0=1`, u32 BE target | confirmed, 3 moves | [registers.md](registers.md) |
| Position is u32 BE in register `0x03` | confirmed | [registers.md](registers.md) |
| Register `0x0C` = **serial number**: `0x6000` + the ESP32's MAC | confirmed vs ASIAIR screen | [registers.md](registers.md) |
| Register `0x04` = FW **3.8.2** + model **EAFN** | confirmed vs ASIAIR screen | [registers.md](registers.md) |
| The EAF serial **contains the ESP32's MAC**, matching the ROM identity | confirmed | [enumeration.md](enumeration.md) |
| `GET_REPORT` NAKs until ready; `0x0C` needs ~40 polls | confirmed | [registers.md](registers.md) |
| **Halt** is the same write with `b0=0, b6=0`; position field ignored | confirmed, 3 cycles | [registers.md](registers.md) |
| **Sync**: the same write with `b0=0, b6=1` sets the current position | confirmed; an ASIAIR zeroed the persona this way | [registers.md](registers.md) |
| Connected idle: ~1 Hz `0x03` poll, ~0.23 Hz `0x04`, `0x81` NAKed ~125/s | confirmed | [capturing.md](capturing.md) |
| **Temperature** = `(b7..b8 - 30000) / 100` °C | confirmed, 2 anchors | [registers.md](registers.md) |
| **b9 carries the Reverse setting**, bit `0x02`; the device stores and echoes it | confirmed, toggled on then off | [registers.md](registers.md) |
| Travel is 5760 steps | contradicted: a target of 17000 was accepted | [registers.md](registers.md) |
| No max-step field appears in any capture | `0x017530` was misread; `0x7530` is the temperature bias | [registers.md](registers.md) |

HID is good news. Fixed-length reports are far easier to emulate on TinyUSB than
a vendor bulk protocol, and the report descriptor is readable from any host with
no driver at all.

## Hardware is available

A real ZWO EAF is owned and wired through the Cynthion, with the ASIAIR as host.
Capture is live and scriptable: see [capturing.md](capturing.md). Earlier notes
in this file assumed no EAF was available and recommended static analysis of
ZWO's SDK instead. That is now a cross-check, not the primary route.

The SDK route stays useful for one thing: naming. `EAFOpen`, `EAFMove`,
`EAFGetPosition`, `EAFStop`, `EAFGetTemp` give documented entry points to match
against whatever the captures show, which is faster than deducing intent from
bytes alone.

## Rule out first

Read the Gemini's own USB descriptors before any of the above. If it clones
ZWO's VID/PID and the ASIAIR rejects it for a narrower reason (serial number
format, firmware version report, a HID report the clone gets wrong), this whole
project shrinks to patching a few bytes, and Facedancer on the Cynthion could
prove that in an afternoon with no ESP32 at all.

## Open questions

Enumeration is answered; see [enumeration.md](enumeration.md). What remains:

- Registers beyond `0x03`, `0x04`, `0x0C`, `0x0D`.
- Does the ASIAIR gate on serial number or the version triplet?
- What reports 2 and 4 carry. Still never used in any capture.
- **Reaching the ESP32 ROM.** The ~0.8 s window is not reachable through macOS's
  tty layer; no port ever appears. See [enumeration.md](enumeration.md) for the
  three options (Linux host, wire-level confirmation, or forcing download mode).

## Capture method

1. Cynthion between the ASIAIR and the EAF, `zwoproxy capture` writing to
   `captures/`. See [capturing.md](capturing.md).
2. Exercise one action at a time on the ASIAIR (connect, read position, move in,
   move out, halt, read temperature). Note the timestamp of each.
3. Decode with `host/` tooling, diff captures against `01-enumerate.pcap`.
