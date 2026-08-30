# ZWO-EAF-Proxy

Makes a non-ZWO focuser appear to an ASIAIR as a ZWO EAF.

A microcontroller enumerates on the ASIAIR's USB bus using the EAF's identity and
protocol, translates incoming focuser commands, and drives the real focuser on
the other side. It must be a USB *device*, which needs native USB peripheral
silicon rather than a USB-serial bridge.

**Two microcontrollers are supported in parallel**, so you can build with what you
have. ESP32-S3 is validated: a real ASIAIR has accepted and driven it. RP2040 is
planned and untested; its PIO can bit-bang a second USB port, which collapses a
two-board design into one.

Only the entry point is chip-specific. Descriptors, protocol and the focuser
interface are shared and their tests build without an embedded toolchain. See
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

How the focuser is reached depends on what it exposes. One board is enough for
anything with a reachable serial port. A USB-only focuser needs a second board
acting as USB host, because the S3 has a single USB peripheral and the persona
side has already claimed it. An RP2040-based board may solve this once tested.

```
                     DS18B20 temp probe
                            │
                            v
  ASIAIR ──USB──>  XIAO ESP32-S3  ──UART──>  focuser with a serial port
                   (EAF persona)             myFocuserPro2, Gemini via HBX
                            │
                            └────UART──>  XIAO ESP32-S3  ──USB host──>  USB-only focuser
                                          (board B)                     Pinefeat CEF
```

The temperature probe is not decoration. The ASIAIR uses focuser temperature for
autofocus compensation, and a Canon EF lens on a Pinefeat has no sensor at all,
so the proxy supplies a real one.

## Status

The EAF protocol is decoded and an ESP32-S3 emulating it is accepted and driven
by a real ASIAIR. No focuser is attached yet: the emulator drives a simulated
one, and the real backends are next.

- [x] Capture a real EAF talking to an ASIAIR (Cynthion, scripted via `zwoproxy capture`)
- [x] Decode the transport: descriptors, HID report layout, control-transfer framing
- [x] Model the command set: position, absolute move, halt, temperature, identity, serial
- [x] Emulate the device on ESP32-S3 and get the ASIAIR to enumerate it
- [x] ASIAIR drives it: firmware 3.8.2, model EAFN, serial, temperature, moves, halt
- [x] Pinefeat retarget test: the pseudo-halt works, 11-12 steps against a 353-step envelope
- [ ] Probe the Gemini's HBX port
- [ ] myFocuserPro2 host backend
- [ ] Persona on a XIAO with the myFocuserPro2 backend: first complete proxy, one board
- [ ] Pinefeat backend (needs a second board for USB host, or a RP2040-based board)
- [ ] Gemini backend
- [ ] Temperature probe on the proxy, for backends that have none
- [ ] Closed-loop test against ASIAIR autofocus

The protocol is in [docs/protocol/](docs/protocol/), the emulator in
[specs/features/001-eaf-persona-emulator.md](specs/features/001-eaf-persona-emulator.md).

Backlash and step limits remain unmodelled, and no limit field appears in any
capture.

Facedancer on a Cynthion presents the same emulator from the desktop and is
useful against macOS and Linux, but an ASIAIR will not enumerate anything it
presents, including Facedancer's own example device.

## Hardware constraint

The part must be a device on the ASIAIR's USB bus, not a USB-serial bridge. That
requires native USB peripheral silicon. Within the ESP32 family it means
**ESP32-S3** or S2; the classic ESP32 and the C3 cannot do it. The board in use is
a Seeed Studio XIAO ESP32S3, and it is what a real ASIAIR has driven.

The S3 has one USB peripheral and the persona claims it, so backends cannot use
USB. Two of the three focusers are sealed metal with no UART to tap, which makes
the backend transport an open hardware question rather than a detail.

An RP2040 would sidestep that: its PIO can bit-bang a second USB port, collapsing
a two-board design into one. Nothing has been tested on it. See
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Design

Two independent axes, meeting at a device-type interface. Adding a focuser is a
backend, and that is the only axis that grows here. A filter wheel proxy belongs
in its own repo, reusing this split. Full detail in
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

```
            persona                 core                    backend
ASIAIR --USB--> EAF emulation --> Focuser iface --> Pinefeat / Gemini / myFP2
                EFW emulation --> FilterWheel iface --> (a separate repo)
```

The backend column is the plan. Only the simulated focuser is written.

The same interface exists twice: in firmware and in the Python host module. That
lets the protocol be exercised without flashing anything.

```
  device side   macOS / Linux ──USB──> Cynthion (Facedancer) <──USB── Mac: zwoproxy
                exercises the persona against a real USB host, no firmware.
                An ASIAIR will not enumerate it; only the ESP32-S3 reaches one

  client side   Mac: zwoproxy ──USB──> a real ZWO EAF, or the proxy
                would drive both with the same commands, so the two can be
                diffed. Not built yet
```

## Layout

- `firmware/` ESP-IDF project, TinyUSB device stack
- `host/` uv-managed Python package: capture decoding, protocol models, and the
  persona over Facedancer
- `docs/ARCHITECTURE.md` design and the USB host-vs-device conflict
- `docs/optical-trains.md` per-train settings to record, and how to measure them
- `docs/protocol/` reverse-engineering notes, one file per finding
- `captures/` pcap captures, gitignored (large, and they carry device serials)

## Target focusers

None are written yet. The persona drives a simulated focuser today.

| Backend | Where | Transport | Why this order |
|---|---|---|---|
| Pinefeat CEF | firmware | USB CDC, sealed case | **main target**: focus and aperture on a Canon EF lens |
| Gemini EAF | firmware | sealed case; try HBX, else a USB host | equal target: the device that motivated the project |
| myFocuserPro2 | host, then firmware | UART tap, DIY board | last by usefulness, first by reachability |

myFocuserPro2 is the only backend needing nothing but a UART, which makes it the
cheapest route to a complete proxy on one board. It goes into the host module
first, to exercise the interface against real hardware. See
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Host tooling

```bash
cd host && uv sync && uv run pytest
```

`zwoproxy capture` records USB traffic through the Cynthion; `zwoproxy persona`
presents the emulator from the desktop. Read
[docs/protocol/capturing.md](docs/protocol/capturing.md) before capturing,
especially the VBUS warning.

`tools/probe_pinefeat.py` talks to a Pinefeat CEF over USB CDC with no
microcontroller in the path, and `tools/fake_cef.py` runs it against a simulated
controller so it can be changed with no hardware attached.

## Firmware

ESP-IDF v5.5, activated per shell so it stays off the global PATH:

```bash
. /path/to/esp-idf/export.sh
cd firmware && idf.py set-target esp32s3 && idf.py build
idf.py -p /dev/cu.usbmodemXXXX flash
```

Reported serial, firmware version and simulated focuser behaviour come from
`idf.py menuconfig` under "ZWO EAF persona", so no unit's serial is compiled in
from this repository.

Descriptor and protocol conformance runs on the build host with no board and no
ESP-IDF, against the same captured bytes the Python side uses:

```bash
firmware/test/host/run.sh
```

**Once flashed, the persona claims the native USB peripheral and the
USB-Serial-JTAG disappears.** Reflashing needs BOOT held while resetting. That is
the same behaviour the real EAF shows.

## Licence

Apache-2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).

## Legal note

Reverse engineering an interface for the sole purpose of interoperability is
permitted in the EU under Directive 2009/24/EC Art. 6. This project reimplements
an interface; it does not redistribute ZWO firmware, SDK binaries, or code.

ZWO, ASIAIR and EAF are trademarks of ZWO. This project is not affiliated with,
endorsed by, or supported by them.
