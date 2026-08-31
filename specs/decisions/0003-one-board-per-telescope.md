# 0003 — One board per telescope, permanently attached

## Context

A proxy carries state that belongs to the focuser it drives: current position,
travel limits, backlash, calibration. None of it is derivable, all of it differs
per optical train, and nothing upstream remembers it. The EAF protocol has no
field for any of it and the ASIAIR has no concept of a train.

Treating the proxy as a shared accessory, moved between scopes, means restoring
that state by hand every time. A microcontroller costs a small fraction of the
focuser it drives, let alone the mount.

## Choice

One board per telescope, mounted and wired to that focuser, and left there. Its
non-volatile storage holds that scope's state and never sees another.

The serial reported by register `0x0C` is derived at runtime from the board's own
MAC, which is what the real device does: `0x6000` followed by the MAC of the
ESP32 inside it. Nothing is compiled in.

## Consequence

How much state that saves depends on whether the focuser's configuration is
fixed. Where it is, as with a stepper wired to one drawtube, travel and backlash
are permanent properties of that scope and live in NVS for good, leaving only the
autofocus step and Reverse in `docs/optical-trains.md` because no register carries
them.

Where it is not, the saving is small. A Pinefeat CEF is dedicated to one scope
but its lens changes underneath it: travel spans 808 to 3970 steps across
different glass and infinity moves with focal length. Travel is rediscovered by
calibration on every configuration and needs no storing, and the values that
cannot be discovered, infinity and the aperture the user wants, remain per lens
and stay in the trains table.

Every board is distinguishable without configuration, and no unit's serial can
reach the repository because none is stored there.

Any host that drives a ZWO EAF drives one of these, so the same hardware serves
NINA through ZWO's ASCOM driver and KStars through INDI. That is a consequence of
emulating faithfully, not a second product: this project writes no drivers.

Untested: whether a host copes with two proxies present at once. Distinct serials
make them distinguishable, but the ZWO ecosystem probably assumes a single
focuser. Only answerable with two boards built.

## Revisit when

A build wants one proxy shared across scopes, at which point the state has to
move off the board and the per-train settings become a stored profile keyed to
something the hardware can identify.
