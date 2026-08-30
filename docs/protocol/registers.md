# EAF register map

Source: `captures/03-move-halt.pcap`, 2026-08-29. Device at address 9, no
re-enumeration during the capture. 112199 packets, 347 control transfers, three
completed moves.

Framing and transport are in [enumeration.md](enumeration.md). Recap: commands go
out as `SET_REPORT` feature report 3, replies come back as `GET_REPORT` feature
report 1, both 16 bytes, both prefixed `<report id> 7E 5A <register>`. Endpoint
`0x81` was polled 6145 times in this capture and **NAKed every one**. It is never
used.

## Access pattern

```
read   OUT  03 7E 5A 02 <reg> 00 …          reply IN 01 7E 5A <reg> <12 bytes>
write  OUT  03 7E 5A <reg> <12 bytes>       no reply
```

Register `0x02` is the read accessor; its first argument names the register to
read. A write addresses the target register directly.

The ASIAIR polls register `0x03` hard while a move is in flight and interleaves
identity reads of `0x04`. It also polls it while the focuser sits stationary but
connected, though less densely.

## Register 0x03 — state block, read/write

The 12-byte body, identical in both directions:

| Byte | Field | Notes |
|---|---|---|
| b0 | moving / go | read: 1 while moving. write: 1 = move, 0 = halt or sync, see b6 |
| b1 | — | always `00` |
| b2..b5 | **position, u32 big-endian** | read: current. write: absolute target **when b0=1**; ignored when b0=0 |
| b6 | **sync flag on a write** | with `b0=0`: `1` sets the current position, `0` halts |
| b7..b8 | **temperature**, u16 BE, `(v - 30000) / 100` °C | `0x8052` = 28.50 °C |
| b9 | **settings bits** | bit `0x02` = Reverse. Bit `0x01` always set. Written by the host, stored and echoed by the device |
| b10..b11 | `0x7530` = 30000, the temperature bias | constant in every read and write |

### Moves are absolute, and confirmed

Three writes with `b0=1`, each followed by a position trajectory that lands on
exactly the value written:

| Write | b0 | target | Observed |
|---|---|---|---|
| `01 00 00 00 03 E8 00 …` | 1 | 1000 | climbed 0 → 1000, `moving` 1 → 0 on arrival |
| `01 00 00 00 00 00 00 …` | 1 | 0 | fell 1000 → 0, `moving` 1 → 0 on arrival |
| `01 00 00 00 42 68 00 …` | 1 | 17000 | climbed 0 → 599, capture ended mid-move |

So `b0=1` plus a u32 in b2..b5 is **move to absolute position**. The target is not
a step count and not a direction; direction is implied by target versus current.

Note the device accepted a target of 17000, so the 5760-step travel figure from
the manual is not what this unit is configured for. **No step limit appears
anywhere in any capture.** The `b9..b11` bytes once floated as a candidate turned
out to be the temperature bias; see Temperature below.

### Halt is the same write with b0=0

Source: `captures/04-halt.pcap`. Three cycles, each a move to 17000 interrupted
early. There is **no separate halt opcode**; only registers `0x02`, `0x03` and
`0x04` appear in the entire capture.

| Cycle | Move target | Halt write carried | Focuser actually stopped at |
|---|---|---|---|
| 1 | 17000 | 7671 | 7757 (+86) |
| 2 | 17000 | 8841 | 9194 (+353) |
| 3 | 17000 | 10781 | 10892 (+111) |

The position in a halt write is whatever the ASIAIR last read, which is already
stale by the time it is sent. **The device ignores it and simply stops.** That is
not an inference from one case: the focuser finishes *past* the written value
every time and never returns to it, and the overshoot varies with how stale the
read was.

So `b0` is the go/stop bit on its own, and `b2..b5` only means anything when
`b0=1`. For the persona, halt is: stop the motor, then report the position you
actually reached. Do not treat the incoming position as a target.

### Writes have three meanings, not two

Source: `captures/15-zero-position.pcap`, the real EAF driven from the ASIAIR.
The focuser was moved to 5000, then zeroed from the UI:

| Write | Device response |
|---|---|
| `b0=1 pos=5000 b6=0` | travels 10892 -> 5000 |
| `b0=0 pos=5000 b6=1` (x3) | nothing observable: the position it carries is the one the device already has |
| `b0=0 pos=0 b6=1` | **reports position 0 from then on** |

The device sat at 5000 and was told `b0=0, b6=1, position=0`. It did not travel
to zero. It was redefined to be at zero.

| b0 | b6 | Meaning |
|---|---|---|
| 1 | 0 | move to the absolute position in b2..b5 |
| 0 | 0 | halt: stop where you are, the position field is ignored |
| 0 | 1 | **set current position** to b2..b5. Zeroing is the special case |

That explains every earlier `b6=1` sighting. Those writes all carried the
position the device was already at, so they were syncs to the current value and
did nothing observable, which is why they read as an at-rest marker.

**A persona must not treat every `b0=0` as a halt.** Discarding the position on a
sync leaves the focuser holding old coordinates while the host believes it has
been zeroed, and the disagreement surfaces later as focus offsets.

### Not yet identified

- **b7..b8 scale is settled; its dynamic response is not.** See below.

## Temperature

**`°C = (b7..b8 - 30000) / 100`**

Anchored twice against the ASIAIR's own display, at two temperatures:

| ASIAIR screen | raw `b7..b8` | decimal | −30000 | ÷100 | Capture |
|---|---|---|---|---|---|
| 28.5 °C | `0x8052` | 32850 | 2850 | **28.50 °C** | `05-temp.pcap` |
| 30.5 °C | `0x811A` | 33050 | 3050 | **30.50 °C** | `06-temp-warm.pcap` |

A 2.00 °C rise on the display is exactly 200 raw counts, which fixes the scale
at 1/100 °C independently of the bias. Three facts agree:

1. Both readings reproduce the displayed value exactly.
2. The delta between them fixes the scale on its own.
3. The bias 30000 is not a fitted constant. It is transmitted in the same
   message, at `b10..b11` = `0x7530`.

The second row was a prediction before it was a measurement. With the display at
30.5 °C the formula called for `0x811A`, and `0x811A` is what the capture
contained.

That second point also corrects an earlier reading of this block. `b9..b11` was
written up as a single constant `0x017530` = 95536 and floated as a possible step
limit. It is not one field: `b9` is a settings byte, see below, and `b10..b11` is
the temperature bias. **Nothing in any capture supports a max-step value**, and a
move to 17000 was accepted, so no evidence of a limit has been seen at all.

### b9 carries the Reverse setting

`captures/18-reverse.pcap`: the ASIAIR's focuser Reverse toggle was switched on,
then off, with the focuser stationary throughout.

| Time | Direction | b9 |
|---|---|---|
| 0.07 s | reply | `0x01` |
| 9.41 s | write, Reverse switched **on** | `0x03` |
| 13.06 s | reply | `0x03` |
| 21.76 s | write, Reverse switched **off** | `0x01` |
| 25.48 s | reply | `0x01` |

**The device stores it and echoes it back.** The host writes b9, and every
subsequent state reply carries the new value until it is changed again. Bit
`0x02` is Reverse; bit `0x01` is set in every capture taken so far and has no
known meaning.

The write that carries the toggle is otherwise a halt: `b0=0`, `b6=0`, and the
position field holding wherever the focuser already is. Nothing moves. Compare
`captures/17-direction.pcap`, where both an UP and a Down press carry `b9=0x01`
because Reverse was off for that whole capture.

**A persona must store b9 and echo it**, rather than emitting a constant. Both
vehicles here treated `b9..b11` as a fixed tail, so a user toggling Reverse
against the proxy would write `0x03`, get `0x01` back forever, and see the
setting refuse to take.

Only two samples of the Reverse bit exist, so the other six bits of b9 are
unexplored. Do not assume they are unused.

### Resolution

Every value seen so far is a multiple of 50: `2750`, `2850`, `3050`
(27.50, 28.50, 30.50 °C). Three samples is thin, but it suggests the sensor
resolves to **0.5 °C** and reports hundredths. Do not assume finer granularity.

### The sensor lags badly

`captures/05-temp.pcap` warmed the EAF by hand for ~50 s of an 84 s window and
**all 72 reads of register `0x03` were byte-identical.** Not one bit moved.

The temperature had in fact risen: the display read 30.5 °C shortly afterwards,
and `06-temp-warm.pcap` caught the raw value confirming it. So the field tracks,
but the sensor sits inside the housing behind the aluminium body and takes well
over a minute to follow a change at the surface.

Worth knowing for two reasons. A capture aimed at temperature needs minutes, not
seconds. And the persona should not expect a backend's temperature reading to
respond quickly either; the real device does not.

## Register 0x04 — identity, read only

Constant across all 38 reads, and across both enumerations:

```
03 08 02 45 45 41 46 4E 00 00 00 00
│  │  │  ?  E  A  F  N
└──┴──┴── firmware 3.8.2
```

Both readings are confirmed against the ASIAIR's device screen, which shows
**FW version 3.8.2** and **model EAFN**:

- b0..b2 = `03 08 02` is the version triplet, 3.8.2.
- b4..b7 = `45 41 46 4E` is ASCII `EAFN`, the model string.

**b3 = `0x45` is unexplained.** It is an extra `'E'`, so either the field is
`"EEAFN"` and the ASIAIR trims it for display, or b3 is a separate type code that
happens to equal `0x45`. Nothing in the captures distinguishes the two.

This is the first thing the ASIAIR asks for after reading the report descriptor,
so the persona must answer it correctly to be accepted.

### What the ASIAIR does with an empty identity

`captures/10-esp32-hid.pcap` and the ASIAIR's own screen, against an emulated EAF
whose registers all answer empty:

| ASIAIR shows | Because |
|---|---|
| FW version `0.0.0` | register `0x04` returned no version triplet |
| Model `ZWO EAF` | with no model bytes it falls back to a generic name, so `EAFN` genuinely comes from `0x04` and not from the USB strings |
| Temp `N/A` | register `0x03` returned no state block |

The device is listed and accepted. It then reports the firmware as too old to
update in the app and defers to ZWO's PC tool, so an empty identity does not open
a route to capturing the update protocol.

**Worth trying once the registers are implemented:** answer `0x04` with a real
but trailing version, `3.7.0` against the device's `3.8.2`, and see whether the
ASIAIR offers an in-app upgrade instead. That would put the update flow, and
probably the firmware image, on the wire. It is also the only known route to the
reboot-into-bootloader command.

## Register 0x0C — serial number, read only

```
01 7E 5A 0C 60 00 <--- 6-byte MAC ---> 00 00 00 00
            └─────────────────────┘
             0x6000 followed by the MAC
```

Eight bytes at b0..b7, zero padded. Confirmed against the ASIAIR's own device
screen, which displays `SN 6000` + the MAC.

**The last six bytes are byte-for-byte the serial string reported by the ESP32
ROM identity in every enumeration capture**, which is that chip's MAC address. So
the ASIAIR is showing the ESP32's MAC as the EAF's serial number. See
[enumeration.md](enumeration.md); this is the independent confirmation that the
two identities are one chip.

Note the USB string descriptor advertises serial `123456`, a placeholder. The
real serial exists only at protocol level, so the two never had to agree.

> The actual value is deliberately not recorded in these docs. It identifies one
> specific unit and it is a real MAC address. Read it from
> `captures/08-fwcheck.pcap` (gitignored) if you need it.

## Register 0x0D — read only

Returns all zeros with correct `7E 5A 0D` framing, in three captures. It is a
valid register that genuinely reads zero, not a refusal. Meaning unknown.

## Replies are not immediate

`GET_REPORT` NAKs until the device has the answer ready, and how long depends on
the register:

| Register | NAKs observed before the reply |
|---|---|
| `0x03`, `0x04` | few |
| `0x0D` | 7 - 11 |
| `0x0C` | 37 - 51 |

> **Corrected.** This document previously stated that unknown registers reply
> with 16 zero bytes and no `7E 5A` magic, offering the persona "a defined way to
> refuse". That was wrong, and it was a decoder bug rather than an observation:
> the analysis had picked up an early zero-filled packet instead of waiting
> through the NAKs. `0x0C` was returning the serial number all along.
> **No refusal mechanism has been observed in any capture.** A persona must not
> rely on one existing.

## An aside: the ASIAIR leaks uninitialised memory

The first `SET_REPORT` of the capture was:

```
03 7E 5A 02 04 00 E0 97 63 22 3A 22 32 2E 30 22
                              "  :  "  2  .  0  "
```

The command is a valid `read 0x04`; the padding after it is heap residue from
the ASIAIR, here a fragment of JSON (`":"2.0"`). Harmless for us and the device
ignores it, but it means padding bytes are not reliably zero. **The persona must
ignore everything after the arguments a command defines**, not assume zeros.

## Still open

- Whether b7..b8 actually tracks temperature. The scale is anchored, the
  dynamic response is not. See above.
- What the other bits of b9 do, and what bit `0x01` means. Only Reverse is
  identified, from two samples.
- Registers other than `0x03`, `0x04`, `0x0C`, `0x0D`.
- Reports 2 and 4 from the HID descriptor. Still never used.
