# Architecture

Two independent axes. Neither side knows about the other; they meet at a
device-type interface in the middle.

```
            persona                 core                  backend
ASIAIR ──USB──> EAF emulation ──> Focuser iface ──> Gemini / Pinefeat / myFP2
                EFW emulation ──> FilterWheel iface ──> (a separate repo)
```

- **Persona** (ASIAIR-facing): speaks a ZWO device's USB protocol. Owns the USB
  descriptors and the command framing. One per emulated ZWO product.
- **Core interface**: a device-type contract. `Focuser` is the only one here.
  Personas and backends only ever see this.
- **Backend** (hardware-facing): speaks one real focuser's dialect. One per
  supported product. None are written yet; the persona drives a simulated
  focuser.

Adding a focuser is a backend, and that is the only axis that grows here. The
seam is also what would make a filter wheel proxy cheap to start elsewhere: a
separate repo copies the capture tooling, the descriptor handling and this
split, then writes its own persona and its own interface.

## Focuser interface

The surface the EAF persona needs, and all it ever sees. Frozen, and written
twice: `firmware/main/include/focuser.h` and `host/src/zwoproxy/focuser.py`.
`test_focuser_mirror.py` fails if the two drift.

| Operation | Notes |
|---|---|
| `begin()` | open the hardware; false if it is not there |
| `position()` | absolute step count |
| `moveTo(target)` | absolute, non-blocking |
| `halt()` | must be immediate |
| `setPosition(position)` | redefine the current position without moving. How a host zeroes a focuser |
| `isMoving()` | polled by the ASIAIR during autofocus |
| `maxStep()` | no limit field appears in any capture; the real device accepted 17000 against a rated 5760 |
| `temperature()` | hundredths of a degree, or unsupported. See Temperature below |
| `tick()` | drive the backend's own state machine. Called often |

Backends that cannot answer something (Pinefeat cannot read back aperture, some
have no temperature probe) report unsupported rather than faking a value. The
persona decides what to tell the ASIAIR.

**`begin()` and `tick()` are declared and called by nobody today.** The firmware
entry point reaches past the interface to `SimulatedFocuser::advance(elapsed_ms)`,
which works only because the backend is simulated. The myFocuserPro2 backend is
where that has to close: `begin()` opens the UART, `tick()` pumps the dialect's
state machine, and `advance()` will not exist on it. Until then the entry point is
coupled to one concrete backend, which is the coupling this interface exists to
prevent.

## Backends

All three get firmware backends. myFocuserPro2 lands in the host module first.

| Backend | Where it lives | Transport | Framing |
|---|---|---|---|
| Pinefeat CEF | firmware | USB CDC, sealed case, needs board B | ASCII, LF-terminated, e.g. `m5200` |
| Gemini EAF | firmware | sealed case; try HBX, else board B | unknown, ships its own ASCOM driver |
| myFocuserPro2 | host first, then firmware | UART tap, DIY board | ASCII, `:cmd#` |

**Pinefeat is the main target by usefulness.** It gives an ASIAIR focus and
aperture control over a Canon EF lens, which is a capability gap rather than a
substitution. The Gemini matters equally: it is the device that motivated the
project, and the ASIAIR's refusal to drive it is why any of this exists.

**myFocuserPro2 is last by usefulness and first by reachability.** Its OTA is
rarely used, so nobody is waiting on it, but it is the only backend needing
nothing more than a UART. It goes into the host module first, where it exercises
the `Focuser` interface against real hardware and gives something concrete to
diff proxied behaviour against. A firmware backend follows.

That ordering is worth stating plainly, because the two axes point opposite ways.
**myFocuserPro2 is the only backend that runs on a single XIAO**, so it is the
cheapest route to a complete working proxy in firmware: persona, interface and a
real focuser, one board, no USB host. Board B is still required for the Pinefeat
and therefore for the main target, but it does not gate a first working proxy.

### Order of work

Two nearly-free tests came before any hardware purchase, because either could
reshape the project. The first is answered; the second is not.

1. ~~**Host persona over Facedancer.**~~ **Tried, and it does not work.** The
   ASIAIR enumerates nothing that Moondancer presents, including Facedancer's own
   example device: 27 bus resets and not one SETUP packet, reproducibly. The same
   persona enumerates on macOS in three seconds. See
   `specs/features/001-eaf-persona-emulator.md`.

   **The question it was meant to answer has since been answered on the
   ESP32-S3.** An ASIAIR accepts the persona and drives it: identity, serial,
   temperature, absolute moves, halt and zeroing. So Facedancer was the wrong
   vehicle, not the wrong protocol model. The desktop vehicle stays useful
   against macOS and Linux.
2. **Pinefeat retarget test.** Over USB CDC from the Mac, decide whether the
   pseudo-halt works. See [protocol/pinefeat.md](protocol/pinefeat.md). This
   decides whether the main target is viable at all.

Then, in order: probe the Gemini's HBX port; write the myFocuserPro2 host
backend; pair it with the persona on a XIAO, which is the first complete proxy
and needs one board; add board B and the Pinefeat backend; add the Gemini backend
over whichever transport won.

The persona side of that XIAO step is done. What remains is a real focuser behind
it: everything demonstrated so far sits on a simulated one.

### Gemini EAF

Not the Optec Gemini. A ~65 EUR ZWO EAF knockoff: same bracket hole pattern,
same port layout (TEMP jack, USB-B, HBX hand controller), USB-powered 5V.

It ships its own ASCOM driver and works with NINA, KStars and SharpCap, but
**not with the ASIAIR**. That is the whole reason this project exists, and it
also tells us the Gemini does not speak the EAF protocol: if it did, the ASIAIR
would already drive it.

Its dialect is cheap to discover. It is a USB serial device, so it can be probed
from the Mac today, no Cynthion involved:

```bash
ls /dev/tty.usb* /dev/tty.wchusb* /dev/tty.SLAB*
ioreg -p IOUSB -w0 -l | grep -A20 -i gemini
```

Worth ruling out first: read its descriptors. If it turns out to clone ZWO's
VID/PID and the ASIAIR rejects it for some other reason, the project collapses
into something much smaller than a full emulation.

Its case is sealed metal, so there is no UART to tap inside. The **HBX hand
controller port** is the way in worth trying first; see
[Try the Gemini's HBX port first](#try-the-geminis-hbx-port-first).

## Temperature

The ASIAIR uses focuser temperature for autofocus temperature compensation, so
this is a real feature and not decoration. The persona has to fill the field:
register `0x03` b7..b8, `(raw - 30000) / 100` in degrees C.

Backends differ. The Gemini has a TEMP jack. The Pinefeat has nothing, because a
Canon EF lens has no probe, which means temperature compensation is simply
unavailable on it today.

**The proxy can carry its own probe.** There is already an MCU in the path, so an
external sensor on board A closes the gap and gives the Pinefeat a capability it
cannot otherwise have.

Precedence, which keeps the rule that a backend never fabricates a value:

1. Backend reading, when the backend supports one.
2. The proxy's own probe.
3. Neither: **unresolved.** No capture shows what the ASIAIR does with a missing
   or implausible temperature. Find out before choosing a fallback.

### Sensor choice

Use an external probe on a cable, positioned on the tube or lens barrel, which is
what the EAF's TEMP jack is for. **Do not use the ESP32's internal sensor**: it
reads die temperature, the chip heats itself under USB load, and focus would end
up compensated against the proxy's own power dissipation.

A DS18B20 is enough, and the captures say so rather than intuition. Every
temperature the real EAF reported was a multiple of 50, so it quantises to
**0.5 C** despite the wire format carrying hundredths (see
[protocol/registers.md](protocol/registers.md)). A DS18B20 is +/-0.5 C, which
matches the genuine device at the resolution the ASIAIR actually consumes. One
GPIO and a 4k7 pullup. Board A has the pins.

## Pin budget

Both candidate boards expose 11 GPIO. The persona claims the native USB
peripheral, so the USB console disappears and debugging goes over UART: two pins
are spent before anything else. Nine remain.

| Need | Pins |
|---|---|
| Temperature probe, DS18B20 on 1-Wire | 1 |
| Zero button, to ground on an internal pull-up | 1 |
| Backend over UART: myFocuserPro2, or a link to a second board | 2 |
| Backend over PIO-USB instead, on an RP2040 | 2, replacing the UART |

Four of nine either way. Not a constraint. The MAX3421E option was the only
cramped one, wanting six pins by itself.

Three constraints on the wiring:

- **PIO-USB needs two consecutive GPIO numbers** for D+ and D-, and the XIAO
  silkscreen order does not follow GPIO order. Find a consecutive pair that is
  not the console UART, from the board's own pinout.
- **Keep the button off strapping pins.** A pin held low at reset by a pressed
  button can change boot mode, which is how the board is put into flash mode.
- **Leave an ADC pin free** if a ZWO-style temperature probe is ever wanted. The
  EAF's TEMP jack is almost certainly a thermistor, so an analog input. A DS18B20
  needs no ADC, but designing the option out costs nothing to avoid.

The zero button should require a long press. Zeroing absolute position by
accident mid-session has no undo.

This has a protocol counterpart. Byte 6 of register `0x03` is the sync flag: a
write with `b0=0, b6=1` sets the current position, which is how the ASIAIR zeroes
a focuser; see [protocol/registers.md](protocol/registers.md). The host can
already zero it, so the button is a local equivalent.

## The USB conflict

The ESP32-S3 has one USB-OTG peripheral. It can be host or device, not both. The
persona side must be device, so the backend side cannot use USB.

All three backends are USB devices. An earlier version of this document assumed
all three could therefore be reached by tapping a UART inside the enclosure. That
is **wrong**: the Gemini and the Pinefeat are sealed in metal cases with no
serial pins reachable. Only myFocuserPro2 can be tapped, because it is a DIY
build.

| Backend | Enclosure | Backend transport |
|---|---|---|
| myFocuserPro2 | DIY, open | UART tap upstream of its USB-serial bridge. The one backend needing no extra hardware |
| Gemini EAF | sealed metal | **HBX port if it carries serial**, otherwise a USB host |
| Pinefeat CEF | sealed metal | needs a **USB host** on the backend side |

So the real constraint is not "tap a UART", it is: **the sealed backends need a
second USB port that the ESP32-S3 does not have**, unless another externally
accessible port gets there first. That is a hardware decision, not a backend
detail to settle later. The Pinefeat needs it outright. The Gemini may not, which
is why its HBX port is worth checking before anything is designed.

### Try the Gemini's HBX port first

Before designing in a second USB port, check whether the Gemini needs one at all.
Its port layout is TEMP jack, USB-B, and an **HBX hand controller** socket. A hand
controller port is externally accessible and is very likely a plain UART or I2C,
which is how ZWO's own EAF drives its hand controller.

If the Gemini's HBX carries something tappable, the motivating device is solved
with a cable: no case opening, no USB host, no extra silicon. That would leave
only the Pinefeat needing board B, and it is a cheap experiment either way.

Cheap to test. Put a logic analyser or scope on the HBX pins while the Gemini's
own ASCOM driver drives the focuser, and look for serial. **Do this before
committing to any of the options below.**

### Options for a backend USB host

Needed for the Pinefeat regardless, and for the Gemini if HBX comes to nothing.

1. **Two ESP32-S3 back to back.** Board A is the persona (USB device to the
   ASIAIR), board B is USB host to the focuser, and they meet over UART. Best
   general option, mainly because Espressif maintains exactly the host drivers
   this needs: `usb_host_cdc_acm` covers the Pinefeat, and
   `usb_host_ch34x_vcp` / `usb_host_cp210x_vcp` / `usb_host_ftdi_vcp` cover
   whichever bridge chip the Gemini uses. One toolchain, no exotic parts, two
   wires plus ground between the boards.

   The split maps onto the `Focuser` seam that already exists: the interface
   becomes a wire protocol instead of a function call, and neither side learns
   anything about the other.

   **VBUS is the thing to check.** A host must power its device, and the XIAO's
   USB-C VBUS ties to its 5V pin, so board B has to source ~500 mA for the
   focuser. Budget that against what the ASIAIR's port will give, since it is
   now feeding two boards and a motor.

2. **MAX3421E over SPI.** Keeps one MCU. TinyUSB ships a MAX3421E host driver
   and USB Host Shield Library 2.0 has CDC-ACM and bridge-chip class drivers.
   Costs roughly six pins (SCK, MISO, MOSI, CS, INT, RST) out of the XIAO's 11,
   and the myFocuserPro2 UART wants two more. Check the pinout before committing.

3. **A single RP2040 doing both roles.** Its native USB controller runs the
   persona while its PIO bit-bangs a second USB port through Pico-PIO-USB for the
   backend. TinyUSB supports that pairing and ships dual device-plus-host
   examples. **This collapses the two boards into one**, which is the real prize:
   less wiring, less power, a simpler enclosure. A XIAO RP2040 is the same form
   factor as the board already in use.

   The persona code ports cheaply. The descriptors, codec and register dispatch
   carry no ESP-IDF and their tests already compile with plain `c++`; only the
   entry point is toolchain-specific.

   Three risks, in order. **Vendor bridge chips**: Espressif maintains host
   drivers for CH34x, CP210x and FTDI, and TinyUSB's host-side coverage of those
   is thinner. That does not touch the Pinefeat, which is CDC-ACM, but the Gemini
   is a bridge chip. **PIO-USB is fussier than a hardware controller**: full speed
   only, and it wants the part clocked at 120 MHz with PIO and DMA committed to
   it. **VBUS**, as ever: two GPIO plus 5 V and ground to a USB-A socket, powered
   through the host's port.

   Evaluate this when the Pinefeat backend starts, not before. The decisive test
   is cheap and needs no persona: get PIO-USB host talking CDC-ACM to a Pinefeat
   on a bare RP2040. If that works, porting the persona is the easy half.

4. **An RP2040 as a host bridge only**, with the ESP32-S3 keeping the persona.
   Falls between the two above and inherits the second toolchain without the
   single-board payoff. Listed for completeness.

5. **A main MCU with two USB ports in hardware.** Cleanest, and discards the
   ESP32-S3 assumption the project is built on. Only if the others fail.

Note the ESP32-S3 cannot bit-bang USB host itself: no PIO, and its single
USB-OTG peripheral is already committed to the persona. Cutting a USB cable and
wiring D+/D- to GPIO does not help either. Those lines carry 12 Mbps NRZI USB
signalling, not serial, and the UART only exists between the bridge chip and the
MCU, both sealed inside the enclosure.

This is the one choice that is expensive to reverse. Decide it before committing
to a board layout.

### Framework: ESP-IDF

Either PlatformIO or plain ESP-IDF works, and both build natively for Apple
Silicon, so the development machine does not decide this. What decides it is that
the USB host VCP components are ESP-IDF components: trivial to add with
`idf.py add-dependency`, fiddly from Arduino-under-PlatformIO.

The Pinefeat is the main target and it needs a USB host whatever happens with the
Gemini's HBX port. So **ESP-IDF** is the choice for the ESP32-S3 vehicle: both USB
roles first-class, no dependency on the community PlatformIO fork that tracks
IDF 5.x.

If option 3 above wins, the second board disappears and so does this choice: the
RP2040 SDK replaces it. The persona is written to survive that. Its descriptors,
codec and dispatch carry no ESP-IDF and their tests compile with plain `c++`, so
a port is mostly the entry point.

Nothing blocks on this immediately. The first two experiments run on the host, and
the first firmware milestone is the persona against a stub backend, which builds
the same either way.

## Two microcontrollers, in parallel

Both are supported rather than one being chosen, so a builder can use the part
they have. Neither dominates: the ESP32-S3 has Espressif's maintained USB host
drivers for the bridge chips a sealed focuser hides behind, and the RP2040 does
both USB roles on one part.

| | ESP32-S3 | RP2040 |
|---|---|---|
| Status | validated against a real ASIAIR | planned, untested |
| Persona side | native USB device | native USB device |
| Backend over USB | second board, or a host controller | PIO-USB on the same part |
| Vendor bridge chips | maintained VCP drivers | thinner coverage |

The cost is that every backend is validated twice, and PIO-USB's handling of
vendor bridge chips is the thin spot. The saving is that most of the work is
already shared: descriptors, protocol codec, register dispatch and the `Focuser`
interface carry no toolchain, and their tests build with a plain host compiler.
Only the entry point is chip-specific.

**Keep it that way.** A toolchain dependency that leaks out of the entry point is
what would make the second path expensive.

## Target board

Seeed Studio XIAO ESP32S3 (ESP32-S3R8, 8 MB flash, 8 MB PSRAM, USB-C, 11 GPIO).

Its USB-C port is the native USB peripheral, so once the persona claims it in
device mode the USB-Serial-JTAG console disappears. That is exactly the behaviour
the real EAF shows in `docs/protocol/enumeration.md`: it boots as the ESP32 ROM
serial/JTAG device, then re-enumerates as ZWO. Debugging the persona therefore
has to go over a UART, not the USB console.
