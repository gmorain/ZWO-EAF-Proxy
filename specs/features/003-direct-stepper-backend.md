# 003 — Direct Stepper Backend

Status:  planned

---

## User

The proxy drives the focus motor itself. A 28BYJ-48 stepper and its ULN2003
driver board stay mounted on the telescope, and the board stays with them: one
proxy per scope, wired once and left there, the way an EAF would be. The ASIAIR
sees a ZWO EAF and moves the focuser; nothing else is in the path.

This is the whole proxy on one board. No USB host, no second microcontroller, no
serial dialect between the persona and the motor, and no case to open. Four wires
from the board to a driver already fitted to the scope.

Focus position survives a power cycle. There is no encoder and no home switch, so
the proxy counts steps and remembers where it left off. Travel limits, backlash
and position all belong to that telescope and stay on its board, so nothing is
re-entered when you move between scopes.

What it cannot survive is the focuser being moved while the proxy is not driving
it. Coils are released at rest, so the mechanism turns by hand, and a knock in
transport moves it too. Nothing detects either, and the stored count is then
confidently wrong. A real EAF behaves the same way.

Recovering is manual and takes one minute: move the focuser by hand to its zero
end, then set the current position to 0, from the ASIAIR or with the proxy's own
zero button. The count is assigned directly, nothing moves, and the scope is
back in step.

Travel limits are yours to set. The mechanism has physical ends and nothing
detects them, so a move commanded past the end grinds the motor against the stop
and loses steps silently, after which the reported position is wrong until you
zero it again. Configure the limits once per telescope and the proxy refuses to
drive past them.

## Tech

- **Wiring.** Four GPIO to IN1..IN4. ULN2003 inputs are Darlington bases behind
  series resistors and switch from 3.3 V logic. Motor supply is 5 V.
- **Phase order is IN1, IN3, IN2, IN4.** The middle two swap relative to the
  silkscreen. Wired in silkscreen order the motor buzzes and does not turn. HBG3
  passes exactly that order to AccelStepper's HALF4WIRE constructor.
- **Pin budget.** Four of the nine that remain after the console UART, alongside
  the DS18B20 and the zero button. See `docs/ARCHITECTURE.md`.
- **Prior art.** HBG3 (https://github.com/Mraanderson/HBG3) emulates a Celestron
  focus motor over the same ULN2003 and 28BYJ-48, and is the reference for coil
  power, presence detection and limit handling below.
- **The backend owns position.** No controller to ask, so the step counter is the
  authority. `position()` is exact by construction and `setPosition()` assigns
  the counter. The offset wrapper 002 needs for a backend without a native sync
  does not apply here.
- **The zero button is optional and shares one path.** Both it and the ASIAIR's
  sync call `setPosition()`; the button is a wiring choice and its absence
  changes nothing. Refuse it, or halt first, while a move is running: zeroing
  mid-move redefines the coordinates the host is actively targeting.
- **The host sees a button press within about a second**, through the ~1 Hz
  `0x03` poll it makes anyway. Nothing announces it, because the protocol has no
  way for a device to tell a host anything, so it is indistinguishable from any
  other unexpected position change.
- **No automatic re-homing.** A home switch is not general: an internal-focus
  tube such as a Maksutov moves its primary and has no drawtube to put one on.
  Driving blind into the end stop is worse there, since it can unseat the mirror.
  Recovery is the manual procedure in User, and the zero button exists for it.
- **One board per telescope**, so NVS holds one scope's state for good. See
  `specs/decisions/0003-one-board-per-telescope.md`.
- **Persist on settle.** NVS write when a move completes, never per step: it is
  flash-backed and has finite erase cycles. Without persistence a power cycle
  loses the position entirely, since nothing else knows it. HBG3 writes on every
  change, but to FRAM, and uses a delayed save for the values it keeps in NVRAM.
- **Stepping happens in `tick()`**, one phase transition per due interval, never
  blocking. This is the backend that finally gives `begin()` and `tick()` work.
- **Half-step, eight phase.** Roughly 4096 steps per revolution, the same order
  as the EAF's own step space, so `maxStep` reports the configured travel and
  nothing is scaled. Microstepping is not available: the ULN2003 is a bare
  Darlington array with no current control, so half-step is the floor. HBG3's
  `stepper_microsteps = 8` on this path is a speed multiplier, not microstepping.
- **Rate ceiling of 1000 half-steps per second**, which is HBG3's figure and
  about 15 rpm on this motor. Accelerate at roughly four times that. A stall is
  undetectable and costs position, so the cap is not advisory.
- **Clamp every target to the configured travel.** A real ASIAIR was seen
  accepting a move to 17000 against a device rated 5760, and here an out-of-range
  target drives the mechanism into its end stop. This is a mechanical
  consequence, not a logical one.
- **De-energise whenever the motor is not running.** Holding all phases heats it
  for no gain and the gearbox ratio holds position unpowered. It also leaves the
  focuser turnable by hand, which is wanted on a visual tube and costs an
  undetected drift in the count. Confirm on the
  focuser before relying on that. HBG3 does exactly this for its ULN2003 path,
  and notes a trap worth inheriting: AccelStepper's `disableOutputs()` does
  nothing unless `enableOutputs()` was called first, so initialisation has to
  enable before it disables.
- **Detect whether a motor is attached.** Nothing else in the design can tell.
  HBG3 has the user fit a 1 k resistor between IN1 and IN4 on the driver board,
  then drives one pin and reads the other in both directions; no loopback means
  no motor. All four pins go to INPUT first or the test misreads. That gives
  `begin()` something to fail on instead of stepping into thin air.
- **Backlash.** The gearbox has appreciable play. Approach every target from the
  same direction, overshooting and returning when the move arrives from the other
  side. HBG3 keeps separate compensation values per direction in NVRAM, so one
  figure may not serve both.
- **Power.** A few hundred mA per phase at 5 V, drawn from the ASIAIR's port,
  which is the same VBUS budget that constrains board B. Measure it.
- **Temperature reports unsupported.** The persona substitutes the proxy's probe.
- **Security.** Inherits 001's posture: local USB on owned hardware, no network,
  so authn/authz and rate limiting are n/a because physical access already
  implies control, and there are no secrets or PII. The only new surface is the
  target position arriving from the persona, which is clamped to the configured
  travel before it reaches the motor.
- **Out of this feature.** Other motors and driver boards, microstepping,
  end-stop switches, and the proxy's temperature probe hardware.

## Tasks

(Populated by /lightspec:plan)

<!-- Uncomment as needed:

## Out of scope
(Things deliberately not in this feature, beyond what's in Tech)

## Decisions
(Non-obvious choices made and why. Promote to specs/decisions/ if the
 same decision affects multiple features.)

## Notes
(Free-form: blockers, retro learnings, links to PRs/issues/commits.)

-->
