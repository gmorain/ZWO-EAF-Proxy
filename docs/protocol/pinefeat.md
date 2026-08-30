# Pinefeat CEF protocol

Fully known. Read off the official ASCOM driver source, no reverse engineering
needed: https://github.com/pinefeat/cef135
(`PinefeatCEF/FocuserDriver/FocuserHardware.cs`, `PinefeatCEF/SharedResources.cs`)

## Framing

Line-oriented ASCII over USB CDC. Send the command followed by `\n`, read until
`\n`, strip trailing `\r\n`.

```csharp
SharedSerial.Transmit(message + "\n");
return SharedSerial.ReceiveTerminated("\n").TrimEnd('\r', '\n');
```

Note: the driver's own doc comment claims replies are `#`-terminated. It is stale
boilerplate from the ASCOM template. The code uses `\n`. Trust the code.

Baud rate is not set in the driver, so the port is opened at the ASCOM default.
CDC ignores line coding anyway, but a UART tap would need the real rate measured.

## Commands

| Command | Meaning | Response |
|---|---|---|
| `v` | firmware version | version string |
| `f` | get position | integer, as text |
| `m<N>` | move to absolute position N, clamped to >= 0 | `ok` |
| `e` | is moving | `y` when moving |
| `r` | travel range | `<min>-<max>`; driver parses the last `-` field as max increment |
| `c` | calibrate | `ok` |
| `a` | get aperture range | range string, f-stops |
| `a<F>` | set aperture, formatted `0.0####` invariant culture, e.g. `a3.5` | `ok` |

Status replies: `ok`, `er` (error), `nc` (not connected).

## Consequences for the EAF persona

**There is no halt command.** The driver's `Halt` throws
`MethodNotImplementedException`, and the ASIAIR aborts moves during autofocus.

This looked like a possible dealbreaker. It is not. `captures/04-halt.pcap` shows
what a real EAF halt does (see [registers.md](registers.md)):

| Cycle | Halt commanded at | Focuser stopped at |
|---|---|---|
| 1 | 7671 | 7757 (+86) |
| 2 | 8841 | 9194 (+353) |
| 3 | 10781 | 10892 (+111) |

**The genuine device overshoots its own halt by up to 353 steps and the ASIAIR
accepts it.** Halt is not precise on real hardware and the tolerance is wide, so
a pseudo-halt on this backend only has to land in the same envelope.

The approach: read position with `f`, then immediately write `m<that position>`.

One thing has to hold for it to work: **the CEF controller must accept a retarget
mid-move.** That is testable today over USB CDC straight from the Mac, with no
ESP32, no second board and no Cynthion. Start a long `m`, then send `f` followed
by `m<pos>`, and see whether it stops. Do this before buying hardware for this
backend; it decides whether the backend is viable at all.

**Aperture has no EAF equivalent.** The EAF is a focuser only. Lens aperture is
outside the persona's vocabulary, so it is either dropped or exposed some other
way. Not a phase-one problem.

**No temperature.** The EAF has a probe and reports it; the CEF does not, because
a Canon EF lens has no probe. So autofocus temperature compensation is
unavailable on this hardware today.

The proxy fixes that rather than working around it. There is an MCU in the path
already, so a DS18B20 on board A supplies a real reading from a probe on the lens
barrel. The backend still reports unsupported, honestly, and the persona
substitutes the proxy's own measurement. See the Temperature section of
[../ARCHITECTURE.md](../ARCHITECTURE.md).

This is the one place the proxy is strictly better than the device it wraps.
