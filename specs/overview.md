# ZWO-EAF-Proxy

## What it is

Makes a third-party focuser appear to a ZWO ASIAIR as a genuine ZWO EAF. A
microcontroller enumerates on the ASIAIR's USB bus carrying the EAF's identity
and protocol, translates the commands it receives, and drives the real focuser on
the other side.

The part must be a USB device rather than a USB-serial bridge, which needs native
USB peripheral silicon. Two parts are supported in parallel so a builder can use
what they have: ESP32-S3, validated against a real ASIAIR, and RP2040, planned.

The ASIAIR only talks to ZWO accessories. Someone with a working non-ZWO focuser
has to replace it or do without autofocus. This is the cheap third option. The
EAF is the whole target, and the only one. A filter wheel proxy would be a
separate repository that duplicates the parts worth reusing.

## Primary users

- Owner of a non-ZWO focuser and an ASIAIR, who wants autofocus without buying a
  ZWO EAF. This is the build the repo exists for.
- Astrophotographers with the same problem, who build one from the repo. Docs are
  written for a competent stranger.
- Contributors adding a focuser, who write one backend against the `Focuser`
  interface and touch nothing else.

## In scope

- An EAF persona the ASIAIR accepts and drives, through to working autofocus.
- Firmware backends for the Pinefeat CEF (focus and aperture on a Canon EF lens,
  the main target by usefulness) and the Gemini (the cheap ZWO EAF clone the
  ASIAIR refuses, which is what motivated the project).
- A backend that drives a stepper directly through a ULN2003, with no second
  controller in the path. The whole proxy on one board, and the shortest route to
  a working one.
- A myFocuserPro2 backend, in the host module first and in firmware after. Its
  OTA is rarely used so nobody is waiting on it, and it needs only a UART.
- A temperature probe on the proxy itself, so backends without one still support
  the ASIAIR's autofocus temperature compensation.
- The EAF protocol documented in `docs/protocol/`, derived from captures rather
  than from ZWO's SDK.
- A Python host module that both emulates a ZWO device and drives one, so the
  protocol model is testable before any firmware exists.

## Out of scope

- ASCOM and INDI drivers. The target is the ASIAIR, and the supported focusers
  already ship desktop drivers. A faithful EAF is driven by ZWO's own ASCOM and
  INDI drivers regardless, so NINA and KStars come free; that is a consequence of
  emulating well, not a thing built here.
- ZWO cameras and mounts. The proxy emulates focuser-class accessories only.
- Wi-Fi, Bluetooth, and network control on the ESP32. USB only.
- Redistributing ZWO firmware, SDK binaries, or decompiled code. This
  reimplements an interface, which EU Directive 2009/24/EC Art. 6 permits for
  interoperability.
- Focusers nobody here owns. A backend needs hardware to test against.
- The EFW filter wheel. It is a different device class with a different
  interface, and mixing it in would widen every decision here for a device
  nobody has started. The two-axis design is what makes it cheap to build
  elsewhere: an EFW repo copies the capture tooling, the descriptor handling
  and the persona/backend seam, and writes its own persona and interface.

## Architecture

Two independent axes meeting at a device-type interface. A **persona** speaks one
ZWO product's USB protocol and owns the descriptors and framing. A **backend**
speaks one real focuser's dialect. Neither references the other; both see only
the `Focuser` interface, which exists once per vehicle and is kept in step by
hand. Adding a focuser is a backend, which is the only axis that grows here. A
backend that cannot answer a query reports unsupported instead of fabricating a
value, and the persona decides what to tell the ASIAIR.

One board is dedicated to each telescope and left attached to it. Position,
travel limits and calibration belong to that focuser, nothing upstream remembers
them, and a microcontroller costs a fraction of the focuser it drives. The serial
is derived from the board's own MAC at runtime, as the real device does, so every
proxy is distinguishable with no configuration. That stores a scope's whole state
only where the mechanism is fixed; a lens controller's travel changes with the
glass on it, so those values stay per configuration. See
`specs/decisions/0003-one-board-per-telescope.md`.

The dominant constraint is that the ESP32-S3 has one USB-OTG peripheral and can
be host or device, not both. The persona claims it, so no backend can use USB.
That binds only the backends that are themselves USB devices. A stepper driven
straight from four GPIO is unaffected, and myFocuserPro2 can be opened to tap its
UART, so both run on a single board. The Pinefeat needs a USB host outright, most
likely a second ESP32-S3 bridged over UART. The Gemini needs one too: 
its HBX socket takes an IR receiver, which is input-only and reports no position. 

The host module is designed to work in both directions. On the device side it
presents as a ZWO device from a desktop through a Cynthion, since a desktop has
no USB device controller of its own; this reaches ordinary hosts but not an
ASIAIR, and it is built. The client side, which would drive real ZWO devices and
proxied ones with the same commands so the two can be diffed, is not built yet.
The same Cynthion captures the traffic either way.

Firmware is ESP-IDF with TinyUSB. Host tooling is uv and Ruff. Captures stay out
of git: they are large and they carry device serials.
