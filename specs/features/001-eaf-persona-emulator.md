# 001 — EAF Persona Emulator

Status:  shipped

---

## User

An emulator that a USB host accepts as a genuine ZWO EAF. It reports a firmware
version, a model and a serial, and it answers position, absolute moves, halt and
temperature against a focuser behind it. The host can also zero it, redefining
where the focuser believes it is without moving it.

Host-owned settings are stored and reported back unchanged. The ASIAIR's focuser
Reverse toggle is one of them, so it takes and stays put across reads.

An ASIAIR accepts it, listing the focuser and driving moves, halts and zeroing.

It runs on two vehicles from one protocol model: on a desktop, needing no
firmware, and on an ESP32-S3 in device mode, which is what the finished proxy
ships. The desktop vehicle reaches ordinary USB hosts but not an ASIAIR, which
enumerates nothing it presents.

Behind it sits a simulated focuser, so it can be exercised with no hardware
attached: moves take time at a configurable step rate and can be halted part way.

The reported firmware version is configurable. Matching the release the host
knows about keeps it quiet; setting a lower one makes the host offer an upgrade.

## Tech

- **One model, two vehicles.** The captured descriptor bytes, the report codec
  and the `Focuser` interface are vehicle-independent and shared. They are the
  conformance suite: whatever runs must reproduce those bytes. See
  `specs/decisions/0002-captured-bytes-are-the-contract.md`.
- **Descriptors and register layout** are specified in `docs/protocol/`:
  `enumeration.md` for the descriptor set and framing, `registers.md` for the
  register map, state block, temperature formula and halt semantics. Those
  documents are the authority and are not restated here.
- **Transport.** Commands arrive as HID feature reports and replies are read back
  the same way. The host requests one byte more than the report contains.
  Handlers match on the report type and ID, since a device declaring four reports
  will otherwise catch the ones it never uses.
- **The report ID may not travel with the payload.** See
  `specs/decisions/0001-report-id-outside-the-payload.md`.
- **STALL the device qualifier request** and **never write to the interrupt
  endpoint.** Both are asserted rather than inherited from stack defaults.
  Answering the qualifier advertises high speed; the link is full speed. The
  endpoint is declared and polled continuously, and the real device NAKs every
  poll: all protocol rides control transfers.
- **Ignore trailing padding.** The host leaks uninitialised heap after the
  arguments a command defines. Padding is not reliably zero.
- **A write with the go flag clear is a halt or a position sync**, decided by a
  separate flag. A halt stops where you are and ignores the position it carries;
  the real device overshoots its own halt by up to 353 steps and the host accepts
  it. A sync redefines the current position without moving, which is how a host
  zeroes a focuser. Treating every such write as a halt leaves the focuser
  holding old coordinates while the host believes it was zeroed.
- **Body byte 9 is host-owned settings, not a constant.** Bit `0x02` is the
  ASIAIR's Reverse toggle. The host writes it, the device stores it, and every
  state reply echoes it. Reading `b9..b11` as one fixed tail makes the toggle
  appear to never take: the host writes `0x03` and reads `0x01` forever. A report
  truncated before byte 9 leaves the stored value alone rather than resetting it.
  Only the Reverse bit is identified; the other six are unexplored.
- **No refusal mechanism.** No capture shows the device refusing a register.
  Unknown registers answer with a zero body. Do not invent a refusal.
- **Timing.** Simulated travel integrates a real clock. A sleep whose duration
  rounds below one scheduler tick does not delay, so it cannot be used to measure
  elapsed time.
- **Security.** Local USB emulation on owned hardware driven from a CLI: no
  network exposure, so authn/authz and rate limiting are n/a because physical
  access already implies control. The untrusted input is the host's control
  traffic; bounds-check every setup field and report body before use rather than
  trusting lengths, since padding is known to carry junk. No secrets. The serial
  is a MAC address identifying one physical unit: configurable, defaulting to a
  placeholder, never in the repository and never compiled into an image there.
- **Out of this feature.** Real focuser backends, and emulating the real device's
  reply latency. A filter wheel persona is out of the repository, not just this
  feature; see `specs/overview.md`.

## Tasks

- [x] Present the captured descriptor set, byte for byte
- [x] Conformance tests against the captured bytes, running with no hardware
- [x] Register layer: framing both directions, and every register seen on the wire
- [x] Simulated focuser, with configurable position, speed and temperature
- [x] Configurable serial and firmware version, on both vehicles
- [x] Bounds-checked input, with malformed and junk-padded cases covered
- [x] Register dispatch tested on both vehicles
- [x] Position sync: a zero redefines the reported position without travel
- [x] An ASIAIR enumerates the persona and drives it: identity, serial,
      temperature, moves, halt and zeroing

### Amendment 2026-08: host-owned settings byte

- [x] Parse body byte 9 on a state write, both vehicles
- [x] Store it in the persona and echo it in every state reply
- [x] A report truncated before byte 9 leaves the stored value alone
- [x] Conformance tests from `captures/18-reverse.pcap`, both vehicles

## Decisions

- Unknown registers answer with a zero body and log a warning, because no capture
  shows the real device refusing one and there is no observed behaviour to copy.
- The report descriptor is stored as raw captured bytes rather than rebuilt from
  HID field helpers, so it cannot drift from what the device sent.
- `max_step` reports the maximum the field can express. No limit field appears in
  any capture and the real device accepted a target well beyond its rated travel.
- Conformance tests compile without the embedded toolchain and without a board,
  so drift is caught before anything is flashed.

## Notes

**Position sync verified on hardware.** `captures/16-esp32-sync.pcap`: the ASIAIR
moved the persona to 5000, which it travelled to step by step, then zeroed it.
The reported position went to 0 in a single poll with the moving flag clear. The
same write the real device receives, and the same response.

**The ASIAIR will not enumerate a device presented by Facedancer on a Cynthion.**
Neither this persona nor Facedancer's own example device gets through attach: the
host resets the bus repeatedly and never issues a setup packet. Both enumerate
normally on macOS, and the same descriptors are accepted on an ESP32-S3, so the
fault is in that gateware rather than in the host or the descriptors. The desktop
vehicle stays useful against macOS and Linux. Do not spend time reaching an
ASIAIR with it.

**Recovering the Facedancer gateware.** It wedges after an interrupted run:
device access starts timing out, and the debug interface then times out too.
Reload the bitstream before each attempt; if the debug interface itself is
unreachable, power-cycle the board.
