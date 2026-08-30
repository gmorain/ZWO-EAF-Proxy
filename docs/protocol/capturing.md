# Capturing with the Cynthion

`zwoproxy capture` drives the analyzer gateware directly. Packetry has no CLI
capture mode, so this exists to make the RE loop scriptable. Output is
`LINKTYPE_USB_2_0` pcap, which Packetry and Wireshark both open.

```bash
cd host && uv run zwoproxy capture -o ../captures/NN-name.pcap -s auto -d 30
```

**Packetry must be closed.** It claims the analyzer interface exclusively.
macOS reports the conflict as `LIBUSB_ERROR_ACCESS`, not `BUSY`.

## Wiring

ASIAIR to TARGET-C, EAF to TARGET-A, Mac to CONTROL. The EAF is correctly
invisible in the Mac's `ioreg` output: it is on the analyzed link, not ours.

## Stream format

Read off `cynthion.gateware.analyzer` (top.py, analyzer.py, fifo.py, events.py).
Big-endian throughout.

```
event    0xFF, code:u8, timestamp:u16
packet   length:u16, timestamp:u16, data[length]
```

A length never starts with 0xFF because the maximum is 1027, so the marker is
unambiguous.

### Three things that are not documented anywhere

1. **Records are 16-bit word aligned.** The ring buffer is addressed in words,
   so an odd-length packet is followed by one padding byte. Consume it as data
   and the parser shifts by one, turning runs of events into multi-kilobyte
   pseudo-packets that still look superficially plausible. Regression test:
   `test_odd_length_packet_is_word_padded`.
2. **OVERRUN only clears on disable.** If a capture crashes with the analyzer
   still enabled, the ring buffer overruns and the gateware stops emitting.
   Re-enabling on top of that is a silent no-op producing an empty capture. Always
   write state 0 before enabling.
3. **Synchronous reads lose data.** `libusb_bulk_transfer` returns TIMEOUT *with*
   partial data; python-libusb1 raises before handing it back. Use async
   transfers, which is why `capture()` runs an 8-deep transfer pool.

### Control plane

Vendor requests, recipient INTERFACE, wIndex 0. `SET_STATE` carries the state
byte in wValue, with no data stage.

| Request | bRequest | bmRequestType |
|---|---|---|
| GET_STATE | 0 | 0xC1 |
| SET_STATE | 1 | 0x41 |
| GET_SPEEDS | 2 | 0xC1 |
| GET_MINOR_VERSION | 4 | 0xC1 |

State byte: bit 0 enables capture, bits 1-2 select speed (HIGH `0b00`, FULL
`0b01`, LOW `0b10`, AUTO `0b11`). **Bits 3-7 route VBUS between TARGET-C and
TARGET-A. Never set them.** Toggling them power-cycles the device under test
mid-capture. `test_state_byte_never_touches_vbus_bits` enforces this.

Note: the comment in the gateware's `top.py` says speed `0b11` is LS. It is
wrong; LOW is `0b10` and `0b11` is AUTO. Confirmed against `luna`'s `USBSpeed`.

## Observed so far

The link runs at **Full Speed**, not High Speed.

**A capture is only worth what the operator state says it is.** The first
`02-idle.pcap` was 24575 packets, all SOFs, and was briefly written up here as
"the ASIAIR does not poll when connected". It was wrong: the ASIAIR was not
connected to the EAF in the app at the time. It measured an idle *bus*, not an
idle *focuser*. `03-move-halt.pcap` contradicts it directly, showing register
`0x03` polled repeatedly while the focuser sits stationary.

Record what the operator was doing, and confirm the connection state in the app
before starting. A capture whose preconditions are unknown is worse than no
capture, because it reads as evidence.

The corrected `02-idle.pcap` (30 s, EAF connected in the app, stationary) shows
the real connected steady state:

| Traffic | Count | Rate |
|---|---|---|
| SOF | 25799 | 1000/s |
| Interrupt polls on `0x81` | 3225 | ~125/s, **every one NAKed** |
| `read 0x03` (position/state) | 24 | ~0.93/s |
| `read 0x04` (identity) | 6 | ~0.23/s |
| Writes | 0 | — |

So a connected, stationary EAF still costs a steady ~1 Hz state poll, an
identity read every few seconds, and continuous interrupt polling that never
returns data. The persona has to service all three. Position read constant at
10892, which is exactly where `04-halt.pcap` left the focuser: a useful
cross-check that the register is stable and the captures are consistent.

At full speed there are 1000 SOFs per second. Filter them at decode time, not at
capture time, so the pcap stays a faithful record.

### Timestamps are not trustworthy

The 16-bit hardware counter wraps every ~1.09 ms and `PcapWriter` extends it by
counting wraps, which only works while records keep arriving. Bus-quiet periods
(reset, detach, an idle stretch) lose whole wrap periods. `01-enumerate.pcap`
spans a real ~37.5 s but its pcap timestamps read 7.8 s. **Record order is
exact; absolute time and inter-packet gaps are not.** Do not reason about
durations from these files.

## Captures

One file each, one action at a time, pauses between actions so records can be
attributed.

| File | Status | What to do while it runs |
|---|---|---|
| `01-enumerate.pcap` | **done** | Replug the EAF from TARGET-A. See [enumeration.md](enumeration.md). |
| `02-idle.pcap` | **redone** | Connected in the app, stationary. First attempt was taken disconnected and was discarded. |
| `03-move-halt.pcap` | **done** | Three moves. The 90 s window expired mid-move and missed the halt, hence `04`. |
| `04-halt.pcap` | **done** | Three move-then-halt cycles. Halt solved, see [registers.md](registers.md). |
| `05-temp.pcap` | **done** | Warmed by hand 50 s. Register never changed: the sensor lags by minutes. |
| `06-temp-warm.pcap` | **done** | Taken once the display had actually risen. Second temperature anchor, formula confirmed. |
| `07-absent.pcap` | **done** | EAF unplugged from TARGET-A for ~43 s mid-capture. Link silent throughout, proving the `0x303A` identity belongs to the EAF and not the Cynthion. |

| `08-fwcheck.pcap` | **done** | ASIAIR firmware/version screen with the EAF already up to date. Revealed register `0x0C` (serial) and confirmed `0x04` against the display. No update was triggered, so the reboot-to-bootloader command is still unseen. |

### Wait through the NAKs before decoding a reply

A `GET_REPORT` is NAKed until the device has the answer ready, and `0x0C` needs
around 40 polls. A decoder that takes the first packet after the request reads a
zero-filled buffer and reports it as real data. That produced a wrong conclusion
once already (see the correction in [registers.md](registers.md)). Always walk
forward to the first reply carrying report ID `01`.

### Read long gaps from SOF frame numbers, not timestamps

`07-absent.pcap` turned on measuring a 43 s gap correctly. The pcap timestamps
cannot do it (see above). SOF frame numbers can: they increment every 1 ms and
are exact. They wrap every 2048 ms, so a long gap reads as a small remainder;
recover the real length by comparing total live bus time against the capture
duration and adding the right multiple of 2048 ms.

Budget the window generously. Idle costs nothing but SOFs, and a capture that
ends mid-action wastes the trip to the rig.
