# 002 — Pinefeat CEF Backend

Status:  planned

---

## User

A Canon EF lens on a Pinefeat CEF controller, driven by an ASIAIR as if it were
a ZWO EAF. The ASIAIR lists a focuser, moves it, halts it during autofocus, and
zeroes it. This is the build the project exists for: it gives an ASIAIR focus
control over camera lenses, which it otherwise cannot drive at all.

The lens must be switched to AF. In MF the controller accepts commands and
reports plausible positions while nothing moves, so the proxy refuses to present
a focuser at all rather than pretending.

Not every lens works. One of six tested calibrates to a different travel each
time and cannot be positioned, while passing every check the controller offers.
The proxy detects that and presents no focuser, rather than driving a lens that
will not go where it is told.

Focus travel is per lens, from 808 to 3970 steps across those tested, and
infinity sits near one end. The room beyond it varies with focal length, from
tens of steps on a 100mm to hundreds on an 18mm. Autofocus sweeps both sides of
focus, so the step size has to fit whatever room that lens leaves on the infinity
side. There is no single value that suits every lens.

Nothing needs flashing to change lens. The proxy calibrates on its own at power
up, discovers the travel, and keeps retrying while the lens is in MF or absent,
so switching to AF is enough to bring it up. Changing or zooming the lens is
noticed and recalibrated without intervention.

Settings are per optical train and the user keeps them. Travel, the step size
suited to it, and the Reverse toggle all change when the lens does, and the proxy
reports what the hardware actually is rather than hiding the difference. Changing
train means restoring those settings from your own notes. To make that a copy
rather than a measurement, the proxy logs the lens and its travel at connect.

Aperture is stopped down from wide open at connect, further on a fast lens
than on a slow one. Nothing in the chain can report the current aperture and the
ASIAIR has no aperture concept, so a lens left stopped down by a previous session
would stay that way invisibly, costing light all night with nothing to show why.
It is not adjustable during a session.

Wide open is rarely what you want. Fast lenses show coma, astigmatism and
spherical aberration worst at maximum aperture, and stars are the subject that
exposes them. A fast lens also has light to spare, so it is stopped down further:
an f/2.8 lens opens at f/4, an f/5.6 lens at f/6.3. How much a given lens
actually needs is found by testing it, so the value belongs in the per-train
settings alongside travel and step size.

Temperature comes from the proxy's probe. A Canon lens has no sensor, so the
backend reports none and the persona substitutes a real reading from the board.

## Tech

Protocol facts, the traps, and the open questions live in
`docs/protocol/pinefeat.md`. Not restated here.

- **Transport.** Line-oriented ASCII over USB CDC, `\n` terminated. The codec is
  already written and tested in `host/src/zwoproxy/backends/pinefeat.py` as pure
  functions, for porting to C++ mechanically.
- **Bench tool.** `host/tools/probe_pinefeat.py` drives a real controller from a
  Mac over USB CDC through that codec, and `tools/fake_cef.py` runs it against a
  simulated one on a pty. Every finding in `docs/protocol/pinefeat.md` came from
  it, and it is the bring-up instrument for this feature. Not part of the wheel.
- **The backend needs a USB host.** The S3 has one USB peripheral and the persona
  claims it. Which host arrangement wins is unsettled; see the backend USB host
  options in `docs/ARCHITECTURE.md`. That decision gates the firmware form of
  this feature, not the dialect.
- **`begin()` calibrates twice and compares.** `c` answering `ok` is necessary
  and not sufficient: some lenses calibrate to a different travel every time, pass
  every other check, and cannot be positioned at all. Two calibrations agreeing on `r`
  within about a percent is the only observed way to tell; a good lens repeats to
  0.1%, a bad one varies by a factor of ten. Anything else means no usable focuser,
  which also covers MF and no lens. The failed state is sticky, so retry on a slow
  cadence rather than latching, and a lens switched to AF after boot comes up by
  itself. Two sweeps per connect is the price.
- **Recalibrate when `a` changes.** It reports the aperture range of the current
  configuration and moves on both a lens swap and a zoom. Poll it slowly; the
  reply costs one line. Always recompute the aperture default from the new range.
  Recalibrating is motion for nothing on a zoom, where travel is unchanged, but
  telling a zoom from a swap is unsolved: only a swap changes travel and travel
  is only knowable by calibrating. Sweep unnecessarily rather than run on a stale
  range. A constant-aperture zoom never changes `a` at all, so zooming one is
  undetectable and the user has to reconnect to pick it up.
- **Never calibrate speculatively.** `c` sweeps the lens to its end stop, so
  outside `begin()` and a detected configuration change it would destroy focus
  mid-session.
- **Nothing about the lens is compiled in.** Travel and range are discovered, not
  configured. Kconfig covers the proxy's own identity, never the glass.
- **Moves are discarded until the controller has re-homed.** It can take several,
  and `f` answers plausibly the whole time, so `begin()` ends by commanding a
  target and confirming `f` lands there, retrying until it does. Position is not
  trustworthy before that.
- **Halt is `f` then `m<that position>`.** Measured at 11 to 12 steps of
  overshoot against the 353 a real EAF shows, deterministic across the travel.
- **Direction.** The count increases toward infinity, which inverts the usual
  focuser convention. The backend reports the EAF convention; a user who wants it
  the other way uses the ASIAIR's own Reverse toggle.
- **Sync is an offset, not a motion.** The command set has no set-position, so
  the backend cannot relabel its coordinates. Report `cef + offset` and let a
  sync to N set `offset = N - cef`. Belongs in a wrapper reusable by any backend
  without a native sync, not in this one.
- **Position is not cacheable.** It has been observed changing with no command
  sent. Re-read before answering.
- **`maxStep` is per lens**, and invisible to the ASIAIR: no register carries it.
  A configuration change shows up only as the reported position moving.
- **Reset the offset on a configuration change**, so the position reads 0 at the
  end stop calibration parks at. All of the new travel stays reachable, and 0 is
  an unambiguous signal rather than an arbitrary in-range number.
- **Set aperture explicitly at connect.** It is write-only and survives power
  cycles, so inheriting it means running at an unknown, unreadable value. `a<F>`
  takes a computed number directly and refuses anything outside the reported
  range, so no snapping to marked f-numbers and no clamping needed.
- **Default stop-down scales with the base aperture**, from `f_min` as reported
  by `a`:

      stops = clamp(log2(5.6 / f_min), 1/3, 2)
      f_default = f_min * 2 ** (stops / 2)

  f/1.4 opens at f/2.8, f/2.8 at f/4.0, f/5.6 at f/6.3. The floor keeps a nudge
  on slow glass, the cap stops a very fast lens losing most of its speed.
- **Log the train's identity at connect**, aperture range and travel on one line,
  so the user can record it in `docs/optical-trains.md` against the step size,
  Reverse and aperture that suit it.
- **Moves land within one step.** Never assert equality between commanded and
  reported position.
- **Temperature reports unsupported.** The persona substitutes the proxy's probe.
- **Security.** Inherits 001's posture: local USB on owned hardware, no network,
  so authn/authz and rate limiting are n/a because physical access already
  implies control, and there are no secrets or PII. New surface is the CEF's
  replies, which are untrusted input: bound every read, reject a reply that is
  not the expected shape, and never size a buffer from a device-supplied length.
- **Out of this feature.** Aperture as a session-time control, the Gemini
  backend, and the proxy's temperature probe hardware.

## Tasks

(Populated by /lightspec:plan)

## Decisions

- Report the real per-lens travel. A normalised virtual range, with a per-lens
  scale factor, would keep `maxStep` stable across lens swaps and let one ASIAIR
  step size suit every train. Rejected: it needs virtual position to be
  authoritative to avoid round-trip rounding, fine steps to accumulate so small
  nudges are not silently dropped, and a floor on the factor to keep a step above
  one real step. Three invariants between the host and the hardware, each of
  which fails quietly. Per-train settings held by the user fail loudly instead.
- Aperture defaults to a stop-down that scales with the base aperture, not to
  wide open and not to a flat amount. Aberration severity tracks the cone angle,
  so a fast lens has both more to correct and more light to spare. The rule is a
  heuristic fitted to two published examples, reproducing a 75-300 f/5.6 at f/6.3
  exactly and a 50mm f/1.8 at f/2.8 within a third of a stop. It is a starting
  point, not a judgement: the tested value goes in the per-train settings and
  overrides it.
- Autofocus step size is the user's to set per train, not the proxy's to
  influence. Around 2 suits a lens with roughly 1800 steps of travel and a few
  tens of steps of headroom above infinity, which is where the sweep has to fit.

<!-- Uncomment as needed:

## Out of scope
(Things deliberately not in this feature, beyond what's in Tech)

## Notes
(Free-form: blockers, retro learnings, links to PRs/issues/commits.)

-->
