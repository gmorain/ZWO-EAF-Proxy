# Pinefeat CEF protocol

Command set read off the official ASCOM driver source:
https://github.com/pinefeat/cef135
(`PinefeatCEF/FocuserDriver/FocuserHardware.cs`, `PinefeatCEF/SharedResources.cs`).
Behaviour confirmed against a real CEF135 over USB CDC; the driver does not
document everything the device does. See [Confirmed on hardware](#confirmed-on-hardware).

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

## Confirmed on hardware

A CEF135 with a lens attached, over USB CDC from a Mac. No ESP32, no Cynthion.

| | |
|---|---|
| USB identity | `04D8:E4FE`, "Lens Controller cef135" by "Pinefeat LLP" |
| Firmware (`v`) | `1.6` |
| Travel (`r`) | per lens: `0-1829`, `0-2363` and `0-2530` on the three that calibrate stably |
| Aperture (`a`) | the lens's true range. No command reports the lens's identity |
| Configuration | `a` and `r` together describe the current setup, and both move when a zoom's focal length does |
| Step 0 | front element protruding, minimum focus distance |
| Max step | front element retracted, just past infinity |

**Aperture is write-only and it persists.** `a<F>` sets it and answers `ok`.
Nothing reads it back: the command set has `a` for the range and no equivalent
for the current value, and the ASCOM driver has `GetApertureRange` and
`SetAperture` and nothing else. Set to f/22, unplugged and replugged, the iris
was still closed, so the diaphragm holds its position without power the way a
detached EF lens does.

The combination is a trap. A session inherits whatever aperture the last one
left, no component in the chain can report it, and the ASIAIR has no aperture
concept at all. Someone can integrate all night at f/22 and see only that
everything is dark. A backend has to set aperture explicitly rather than
inheriting it.

**`a<F>` takes any value inside the reported range.** `a3.5279` is accepted, so a
computed f-number needs no snapping to the lens's marked series; the lens rounds
to its own nearest step internally. Outside the range it refuses: `a1.4` and
`a99` both answer `er` against a `2.8-22.6` lens. The range is the lens's own and varies:
six stops for `2.8-22.6` and `5.6-45.2`, seven for `2.8-31.9`.

**Not every EF lens can be driven, and nothing reports it.** A Canon EF 50mm
f/1.8 II passes every check: `a` answers `1.8-22.6`, `c` answers `ok`, `r`
answers a plausible `0-N`. It is still unusable. Five consecutive calibrations,
nothing touched between them, produced travels of 143, 755, 220, 78 and 996.
The step space is different after every `c`, so commanded positions clamp against
whatever range the last one invented, and a move looks wildly wrong when it is
only obeying a range that changed.

A power cycle does not fix it. The controller acquires a range by itself on boot,
`0-996` in that case, so acquisition works; three calibrations afterwards gave
115, 908 and 134. Unstable under both a hot swap and a power cycle.

The two lenses that work calibrate to the same figure every time, 1829 and 2363.
So the detector is **calibrate twice and compare within a tolerance**: a lens
whose travel is not reproducible cannot be positioned. Compare loosely, not for
equality. A 100mm macro repeated six calibrations across 2528 to 2531, a spread
of 0.12%, while the 50mm spanned 78 to 996. A percent of the travel separates the
two cases by three orders of magnitude. A single verification move does not catch
it, because moves are consistent with the range currently in force.

The likely cause is the lens rather than the controller. That model uses a DC
micromotor with coarse position feedback, and calibration has to find both stops
by driving into them. Unconfirmed.

**The lens must be in AF.** In MF the focus element is mechanically decoupled, and
the controller hides it: `m` answers `ok`, `e` answers `y`, and the position
readout moves and settles at values that mean nothing. There is no error and no
status distinguishing the two. Check the switch before believing any reading.

**`r` = `0-65535` means the controller has no focus data for the lens.** It falls
back to the raw 16-bit field when it cannot get one, which covers MF and a lens
swapped in while powered. A power cycle with the lens attached acquires by
itself, and a second lens read that way answered `0-2363` with no `c` sent. A hot
swap does not: a third lens answered `0-65535` in AF until `c` was sent, then
`0-967`.

**Zooming changes `a` and not `r`.** A 75-300 read `5.6-45.2` at 300mm and
`4.1-31.9` at 75mm, updating with no command sent. Travel stayed `0-2363` at both,
and two calibrations at 75mm returned the same figure. The focus group moves the
same physical distance whatever the focal length, so a zoom needs the aperture
default recomputing but not the travel remeasuring. That lens also stayed sharp
on a distant subject at the same step, 2280, at both 75mm and 300mm, so it is
near parfocal in step terms. One lens is not a rule.

**A constant-aperture zoom is invisible to the detector.** A Tokina 11-16 f/2.8
answers `2.8-22.6` at every focal length, so zooming it changes nothing the
controller reports. Focus moves and travel may too, with no signal at all. The
`a`-change trigger only works on variable-aperture lenses.

That lens also collides with a Canon EF-S 24mm f/2.8 STM: identical `a`, and only
travel separates them, 808 against 1829.

Distinguishing a zoom from a lens swap is unsolved. Both change `a`, only a swap
changes travel, and travel is only knowable by calibrating. A hot swap leaves `r`
at `0-65535` and a zoom does not, which would discriminate them, but a swap
followed by a power cycle acquires a valid range and looks like a zoom.

**`a` does not need calibration and `r` does.** The aperture range comes back
correctly while focus data is still missing: the 50mm answered `1.8-22.6`
alongside `r` = `0-65535`. So `a` changes the instant glass is swapped, which
makes it a valid trigger for recalibrating even though the focus range is stale.

**`c` is how a backend detects MF, and the only reliable way.** In MF the
controller keeps whatever lens data it cached in AF, so `r` still answers a
plausible range and `m` is still accepted, which is why the first session's
readings looked sane while nothing moved. Calibration is the one command that
admits the truth:

| Command | AF | MF |
|---|---|---|
| `c` | `ok` | `er` |
| `r` after `c` | real travel, e.g. `0-2363` | `0-0` |
| `m<N>` after `c` | tracks, +/-1 step | `er` |

So `r` carries three distinct meanings: `0-65535` for no lens data, `0-0` for a
calibration that failed, and `0-N` for real travel. The failed state is sticky:
returning the lens to AF does not clear `0-0`, only a successful `c` does, so a
backend must be able to retry rather than latch the first failure. `a` stays
valid throughout, so the lens fingerprint survives a failed calibration. A backend's `begin()` should
send `c` and treat anything but `ok` as "no usable focuser", rather than trusting
`r` or trying to infer health from a move. The cost is that `c` homes the lens,
so `begin()` always sweeps.

**Moves are discarded until the controller has re-homed, and `f` lies meanwhile.**
Commanded to 1000 on a freshly attached lens, it swept to the end stop at 2363
instead; the next `m1000` landed at 999. After a reconnect with the lens parked at
its end stop it took four attempts: three moves left it at 1829, a fourth ran to
0, and every move after that tracked exactly. `r` and `f` both answer plausibly
throughout, so neither reveals it.

**Verify by moving before trusting position.** Command a target, read `f`, and
repeat until one lands where asked. Nothing else distinguishes a controller that
knows where the lens is from one that does not. `c` forces the same re-homing
explicitly and is the cheaper way to do it at connect.

**Moves land within one step.** Seven targets across the range came back with a
delta of 0 or +/-1, exact at both ends. Do not assert equality between commanded
and reported position.

### The count increases toward infinity

Observed by eye, lens in hand, sweeping 0 to 1829 and back three times: at step 0
the front element protrudes, at step 1829 it is retracted into the barrel. A
protruding front group means a longer optical path, which focuses nearer, so step
0 is minimum focus distance and step 1829 is infinity.

**That inverts the usual focuser convention**, where higher numbers rack outward
and focus nearer. It also means `c` is convenient rather than awkward: it parks
the lens at 1829, which is the end astro imaging works at.

**Confirmed on a second lens**, a 300mm f/5.6 with 2363 steps of travel: its
maximum step is also the infinity end, and also slightly past it. So direction is
a property of the controller rather than of the lens, and stays one boolean in
the backend. A user swapping glass does not silently reverse their focuser.

**The persona half turned out not to be a fact at all.** The ASIAIR's focuser
panel has a Reverse toggle, and its buttons are labelled UP and Down rather than
IN and OUT, so it nudges a number rather than expressing a direction. A real EAF
has no inherent direction either: it bolts onto arbitrary focusers through
arbitrary couplings, which is why that toggle exists.

So the backend picks a convention and stays consistent, and a user who finds it
backwards flips Reverse in the app exactly as they would with a genuine EAF. No
invert flag is needed in the backend, and no capture would have settled it, since
a capture only shows what one installation happened to do.

Consistency is still ours to guarantee. Whichever way round it goes, what the
ASIAIR believes and what the lens does must agree, or temperature compensation
walks focus the wrong way all night.

The toggle does reach the device, though it changes no register: it rides body
byte 9 of the register `0x03` write, and the device stores and echoes it. See
[registers.md](registers.md). The persona has to preserve it, but the backend
never sees it and does not act on it.

### The lens focuses past infinity

Measured through the camera on daylight cloud, scanning down from the 1829 end
stop: coarse in twelve steps to 1600, then fine in steps of 5 from 1810 to 1750.
Sharpest fell below the end stop both times, around 1780 on the coarse pass and
nearer 1750 on the fine one.

**Infinity is roughly 50 to 80 steps below the end stop.** The spread is the
measurement, not the lens. Cloud is a poor focus target, being low in contrast
and soft edged, and the judgement was by eye at full aperture where depth of
focus is thin. A hard-edged distant object, or stars, would tighten it.

The imprecision does not affect the design conclusion. Both passes put the sharp
point below 1829, so the lens focuses past infinity and there is real headroom
above focus rather than none. That is what the architecture needed to know.

The 300mm f/5.6 behaves the same way: judged through the camera, its maximum step
of 2363 is past infinity too. Two lenses out of two, so the margin looks like a
property of how the controller places its end stop rather than luck with one
lens. Its size was not measured on the second lens.

A 100mm f/2.8 macro measured the same way puts infinity at 2460 against an end
stop of 2529, so 69 steps. Three lenses with travels of 1829, 2363 and 2530 all land between 50 and 85 steps
of headroom, suggesting a fixed number of steps rather than a fraction of the
travel. **A fourth breaks it.** An 18-200 at 18mm, 3970 steps of travel, focuses
acceptably across roughly 3700 to 3860, so about 170 steps of headroom and a
plateau far too wide to call a peak by eye.

Focal length is the likely reason. Depth of focus grows with the square of the
f-number and shrinks with focal length, so a wide lens at infinity has far more
tolerance than a 100mm macro. Headroom is therefore per configuration and the
autofocus step with it: 5 to 8 on the longer lenses, nearer 17 at 18mm. Measure
it rather than assuming a constant.

The exact step is a property of this lens and shifts with temperature, which is
the whole reason the ASIAIR does temperature compensation. It is not a protocol
constant and should not be treated as one. The measurement that matters in the
end is the ASIAIR's own autofocus, fitting a curve to star HFD.

With the direction inverted so the count matches the EAF's convention, `c` parks
at the end stop, which reads 0, and infinity lands at roughly 50 to 80. Autofocus
then has tens of steps below focus and about 1750 above it.

### The pseudo-halt works

Measured, six cycles, retargeting at two different points into a near-full sweep:

| Retarget at | Commanded at | Stopped at | Overshoot |
|---|---|---|---|
| 0.1 s | 1587 | 1576 | 11 |
| 0.1 s | 1576 | 1565 | 11 |
| 0.1 s | 1581 | 1570 | 11 |
| 0.3 s | 969 | 958 | 11 |
| 0.3 s | 974 | 962 | 12 |
| 0.3 s | 969 | 958 | 11 |

**11 to 12 steps, wherever in the travel it happens.** The real EAF overshoots its
own halt by 86, 353 and 111 steps and the ASIAIR accepts that, so this is inside
the envelope by a factor of about thirty, and it is deterministic rather than
variable. The controller accepts `m<current position>` mid-move without complaint.

The lens is fast: 500 steps complete in under 0.5 s, so a probe has to retarget
within ~0.1 s of starting a full sweep to catch it moving at all.

### Travel is per lens, and small

1829 steps against the EAF's rated 5760, and a real ASIAIR was seen accepting a
target of 17000 (see [registers.md](registers.md)). The persona reports `maxStep`
upstream, so what a backend with 1829 steps should report, and whether the
ASIAIR's step space needs mapping onto it, is an open design question. Nothing in
any capture answers it yet.

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

**Tested on the real controller, and it works.** It accepts a retarget mid-move
and stops 11 to 12 steps past, against an envelope of 353. See
[The pseudo-halt works](#the-pseudo-halt-works). This was the question that
decided whether the backend was viable at all, and it is answered.

**There is no set-position command either.** The command set is `v f m e r c a`,
so the CEF cannot relabel its own coordinates and a sync cannot be implemented
natively. The persona's answer is an offset: report `cef + offset`, and let a
sync to N set `offset = N - cef`. Nothing moves, which is what a sync means, and
the same wrapper serves any backend that lacks a native sync.

Two constraints on that, both from the small travel:

- **Adopt the offset where the reported position is 0.** `c` parks the lens at
  the raw end stop, 1829. Under the direction convention that reads as 0, so a
  zero at connect gives `offset = 0`, the whole travel stays reachable, no extra
  sweep is needed, and the lens is left at infinity where astro wants it. A
  backend reporting raw CEF positions would instead have to sweep to raw 0 first:
  taking the offset at the end stop makes a zero produce `offset = -1829`, and
  since the position field is unsigned and `m` clamps to `>= 0`, every step of
  travel becomes uncommandable.
- **Only when uncalibrated.** If a calibrated focuser at step 1500 is zeroed, the
  travel below it does become unreachable, and that is exactly what a real EAF
  does when zeroed at mid-travel. Mirror it rather than improving on it.

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

## Open questions

Each of these blocks a correct backend rather than a viable one. Viability is
settled.

- **Is 50 to 80 steps of headroom enough for the ASIAIR's autofocus?** That the
  headroom exists is measured; that it suffices is not. The ASIAIR is configured
  in EAF steps, where a real device has over 5760 and this lens has 1829 in
  total, so an autofocus step size chosen for a real EAF may sweep straight into
  the stop and flatten half the curve. Answerable only with the chain assembled,
  and it is the acceptance test for the main target. Related to stopping short of
  a target, below.
- **What does an ASIAIR do when the position jumps?** A lens swap or a zoom
  changes the focus range, so the backend recalibrates and the reported position
  moves without the host asking. Travel itself is invisible to the ASIAIR: no
  capture carries a max-step field and the persona sends none, so position is the
  only thing that can betray the change. Whether the ASIAIR holds a target from
  the previous lens and commands it against the new range is unknown. Not
  capturable against a real EAF, whose travel never changes, so it gets answered
  the first time a lens is swapped with the whole chain running.
- **Position changes with no command sent.** Twice the reported position moved on
  its own. The first time the lens was in MF, which explains it. The second time
  it was in AF and calibrated: `f` read 0 at the end of one session and 1829 at
  the start of the next, minutes later, with nothing sent in between. 1829 is
  where `c` parks, so an idle re-home or a reset on port close both fit, and
  neither is confirmed. Until it is understood, a backend must re-read position
  rather than cache it, and must not assume the lens is where it left it.
- **Stopping short of a target.** With 1829 steps behind an offset, part of the
  ASIAIR's step space is unreachable and a goto past the end has to stop short.
  Captures show the ASIAIR tolerating a 353-step overshoot on a halt; nothing
  shows what it does when a focuser never reaches a commanded position.
  Capturable against the real EAF by commanding past its travel.
