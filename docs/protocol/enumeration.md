# EAF enumeration and control protocol

Source: `captures/01-enumerate.pcap`, 2026-08-29. ASIAIR as host, EAF on
TARGET-A, replugged mid-capture. 38838 packets, 3928 events. The device
enumerates twice in the file (addresses 7 and 9); both rounds are byte-identical,
so either can be read as the reference.

## The EAF is ESP32-based

> This claim was written up as confirmed, withdrawn when a Mac test contradicted
> it, then restored by `07-absent.pcap`. The history is kept below because the
> Mac result is still unexplained in detail and matters to anyone trying to
> reach the ROM.

Two identities appear on the analyzed link, and they are the same physical
device enumerating twice:

| Order | Address | Identity |
|---|---|---|
| first | 6, then 8 after replug | Espressif `USB JTAG/serial debug unit`, VID `0x303A` PID `0x1001` |
| second | 7, then 9 after replug | `ZWO Device`, VID `0x03C3` PID `0x1F10` |

The argument, in order of weight:

1. **No hub ever enumerates.** The replug re-enumerates exactly two identities
   and neither is a hub (class `0x09`). Two devices present at once require a
   hub on a point-to-point link. There is none, so they cannot be concurrent.
2. The Espressif identity is always **first**, is configured, receives
   `SET_LINE_CODING`, and is then **never addressed again** once the ZWO
   identity appears from address 0.
3. Its configuration is CDC control + CDC data + a vendor interface
   `class 0xFF / subclass 0xFF / protocol 0x01`. That is the ESP32
   `USB_SERIAL_JTAG` ROM peripheral, not a generic USB-serial bridge.

That reasoning pointed at one conclusion: the EAF runs an ESP32, boots into the
ROM serial/JTAG identity, then re-attaches as the ZWO HID device.

### The serial number settles it

The ASIAIR's device screen shows a serial of the form `6000` followed by six
bytes. Register `0x0C` returns exactly those bytes (see
[registers.md](registers.md)), and the trailing six are **byte-for-byte the
serial string the Espressif ROM identity reports in every enumeration capture**,
which is that chip's MAC address.

The ASIAIR displays the ESP32's MAC address as the EAF's serial number. Same
chip. This is independent of enumeration order, hub topology, and every USB
timing argument below, and on its own it is conclusive.

Note the USB string descriptor advertises serial `123456`. The real serial exists
only at protocol level, so the two never had to agree, and the fact that this one
does is not a coincidence anyone arranged.

### Ruling out the Cynthion

`captures/07-absent.pcap`, 70 s. The EAF was unplugged from TARGET-A partway
through, left out for ~43 s, then plugged back in.

Read via **SOF frame numbers**, not pcap timestamps. Total live bus time was
27.1 s inside a 70 s capture, so ~43 s carried no bus activity. The frame counter
wraps every 2048 ms, so a long gap reads small: the nominal 18 ms gap at record
25840 is 18 + 21x2048 = **43.0 s**, which accounts for the missing time exactly.

| Records | What |
|---|---|
| 0 - 25840 | EAF connected, SOFs only |
| gap ~43 s | **TARGET-A empty. Zero records. Nothing enumerated.** |
| 25902 | Espressif `0x303A:0x1001` enumerates |
| 26711 -> 26712 | 328 ms bus reset |
| 26774 | ZWO `0x03C3:0x1F10` enumerates |

With TARGET-A empty the link was completely silent. The Espressif identity
appears **only** on EAF attach, on the same physical port, separated from the ZWO
identity by a bus reset. It is not the Cynthion, and it is not a second device.

That is the third independent observation of the sequence (twice in
`01-enumerate.pcap`, once here).

### The Mac test, and why it is the outlier

The EAF was moved to a Mac root port (no hub: `AppleT6000USBXHCI@00000000` ->
`ZWO Device@00100000`) and replugged **four times**, watched by a libusb poll
running every 4 ms. `0x303A` **never appeared**. Only `03c3:1f10`, every time.

Since `07-absent.pcap` rules out a second device, the Mac result is a
**measurement failure, not evidence of absence**. libusb lists only what macOS's
USB stack has fully committed, and macOS enumeration involves several resets and
driver matching. A device that re-enumerates into a different identity after
~0.8 s can plausibly never be registered at all, so nothing would appear in a
libusb poll no matter how fast it runs.

This has a practical consequence: **the ROM window is not reachable through
macOS's tty layer.** No `/dev/cu.usbmodem*` ever appeared across four direct
root-port replugs, so esptool has nothing to open.

### Reaching the ROM

Not yet achieved. Options, in increasing order of effort:

1. **A Linux host.** Enumeration is faster and more transparent, and a
   `/dev/ttyACM*` typically appears within ~100 ms. A tight retry loop firing
   esptool has a real chance inside a ~0.8 s window.
2. **Confirm the window on the wire first.** Cynthion between the Mac and the
   EAF: Mac to CONTROL for the analyzer, Mac to TARGET-C as host, EAF to
   TARGET-A. This shows whether the ROM identity is even offered to a Mac, which
   separates "macOS dropped it" from "the device behaves differently here".
3. **Force download mode.** Hold GPIO0 low at reset. ROM download mode does not
   time out, so the race disappears entirely. Requires opening the enclosure and
   finding the strapping pin, so it is a hardware step, not a software one.

Read-only operations only if it is ever reached: `chip_id`, `flash_id`,
`read_flash`. A stray `write_flash` or `erase_flash` bricks a working focuser.

Note the EFW connected to the ASIAIR is upstream of the Cynthion and cannot
appear in these captures. It is not either of the identities above.

The ASIAIR's serial connection to the ESP32 identity is never used for focuser
traffic in this capture: after `SET_LINE_CODING` it is dropped.

## Device descriptor

```
12 01 0002 00 00 00 40 C303 101F 0001 01 02 03 01
```

| Field | Value |
|---|---|
| bcdUSB | 0x0200 |
| bDeviceClass / SubClass / Protocol | 0 / 0 / 0 (class at interface) |
| bMaxPacketSize0 | 64 |
| **idVendor** | **0x03C3** (ZWO) |
| **idProduct** | **0x1F10** |
| bcdDevice | 0x0100 |
| iManufacturer / iProduct / iSerialNumber | 1 / 2 / 3 |
| bNumConfigurations | 1 |

The link runs at **Full Speed**. `GET_DESCRIPTOR(DEVICE_QUALIFIER)` is **STALLed**,
three times per enumeration. The ASIAIR retries and proceeds; the stall is
expected behaviour for a full-speed-only device and the persona must reproduce
it rather than answer the request.

## Strings

LANGID list is `0x0409` only.

| Index | Value |
|---|---|
| 1 | `ZWO` |
| 2 | `ZWO Device` |
| 3 | `123456` |

The serial number is the literal string `123456`, not a per-unit value. The
ASIAIR re-reads string 3 once more after `SET_CONFIGURATION`. Nothing in the
capture suggests the ASIAIR gates on it, but it does read it twice.

## Configuration descriptor

```
09 02 2200 01 01 00 A0 32          configuration: 1 interface, bus powered + remote wakeup, 100 mA
09 04 00 00 01 03 00 00 00         interface 0, alt 0, 1 endpoint, class 0x03 HID, subclass 0, protocol 0
09 21 1101 00 01 22 4400           HID 1.11, 1 descriptor, report descriptor 68 bytes
07 05 81 03 1000 0A                endpoint 0x81 IN, interrupt, 16 bytes, bInterval 10
```

HID subclass is 0 and protocol is 0: not boot-keyboard, not boot-mouse.

## HID report descriptor (68 bytes)

```
06 00 FF     Usage Page (Vendor Defined 0xFF00)
09 01        Usage (0x01)
A1 01        Collection (Application)
85 01          Report ID 1   95 0F 75 08 26 FF00 15 00 09 01 81 02   Input,  15 bytes
85 02          Report ID 2   95 0F 75 08 26 FF00 15 00 09 01 81 02   Input,  15 bytes
85 03          Report ID 3   95 0F 75 08 26 FF00 15 00 09 01 91 02   Output, 15 bytes
85 04          Report ID 4   95 0F 75 08 26 FF00 15 00 09 01 91 02   Output, 15 bytes
C0           End Collection
```

Four reports, all 15 payload bytes plus the report ID, so 16 bytes on the wire.

## The interrupt endpoint is never used

Endpoint 0x81 is declared and polled for the whole capture and **NAKs every
time**. Zero interrupt IN data packets in 38838 packets. Every byte of protocol
content travels over **control transfers on endpoint 0**:

- Host to device: `SET_REPORT`, `bmRequestType 0x21`, `wValue 0x0303` (feature, report 3), `wLength 16`
- Device to host: `GET_REPORT`, `bmRequestType 0xA1`, `wValue 0x0301` (feature, report 1), `wLength 17`

Note the asymmetry: the ASIAIR asks for 17 bytes but the report is 16. Reports 2
and 4 are declared and never touched in this capture.

The persona must still declare endpoint 0x81 (the ASIAIR enumerates against the
descriptor) but only needs to NAK it.

## Command framing

Every report starts with the report ID, then the magic `7E 5A`, then an opcode.

```
OUT (report 3):  03  7E 5A  <opcode>  <args, zero padded to 15 total>
IN  (report 1):  01  7E 5A  <opcode>  <data,  zero padded to 15 total>
```

Opcode `0x02` reads: its first argument is the register to read, and the reply
carries that register's number in the opcode slot.

## Exchanges observed

In capture order, immediately after `GET_DESCRIPTOR(HID_REPORT)`:

| # | OUT (report 3) | IN (report 1) |
|---|---|---|
| 1 | `7E5A 02 04` | `7E5A 04 03 08 02 45 45 41 46 4E 00 00 00` |
| 2 | `7E5A 02 03` | `7E5A 03 00 00 00 00 00 00 00 00 00 01 75 30` |
| 3 | `7E5A 02 0D` | `7E5A 0D 00 00 00 00 00 00 00 00 00 00 00 00` |
| 4 | `7E5A 02 03` | `7E5A 03 00 00 00 00 00 00 00 00 00 01 75 30` |
| 5 | `7E5A 03 00 00 00 00 00 00 00 00 00 01 75 30` | (no read) |

Reading of these, in descending confidence:

This was the first capture, and the readings below have since been settled by
later ones. They are kept only to show what a single connect handshake looks
like; **[registers.md](registers.md) is the authority on field meanings.**

- Register `0x04` is the identity read and the ASIAIR issues it first, before
  anything else. `03 08 02` is firmware 3.8.2 and `45 41 46 4E` is the model
  `EAFN`, both confirmed against the ASIAIR's own screen.
- Exchange 5 writes register `0x03` with exactly the bytes exchange 4 read back.
  The ASIAIR reads a block, then writes it back unchanged. Register `0x03` is
  read/write and shares one layout in both directions.
- The `00 01 75 30` tail of register `0x03` was read here as a single 32-bit
  field of 95536 and guessed at as a step limit. **That was wrong.** It is two
  fields: `b9` on its own, then `b10..b11` = `0x7530` = 30000, the bias in the
  temperature formula.
- Register `0x0D` returns zeros with valid framing. Still unexplained.

No move, halt or temperature command appears here: the focuser was not driven
during this capture. Those are in `03-move-halt.pcap` and `04-halt.pcap`.


## What this settles

- Product ID is `0x1F10`.
- Transport is HID, vendor usage page, as the docs implied, but carried over
  control transfers rather than the interrupt endpoint.
- The report descriptor, all four report IDs, and their sizes are known.
- The ASIAIR's connect handshake is: standard enumeration, stall the device
  qualifier, `SET_IDLE`, read the report descriptor, then identity read `0x04`.

## Still open

- Register map beyond `0x04`, `0x03`, `0x0D`.
- Move, halt, position and temperature opcodes.
- What the 95536 field means.
- Whether the ASIAIR gates on serial number or the version triplet.
- What reports 2 and 4 are for.
