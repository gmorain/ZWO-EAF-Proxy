# 0001 — The HID report ID travels outside the payload

## Context

The EAF protocol frames every message as `<report id> 7E 5A <register>` followed
by twelve bytes, and that is what appears on the wire. A persona reproducing it
must put exactly those sixteen bytes on the bus.

USB device stacks do not necessarily hand the payload over intact. TinyUSB
carries the report ID separately: it prepends the ID on `GET_REPORT`, and strips
it into a callback argument on `SET_REPORT`.

## Choice

The codec speaks whole wire reports, including the report ID, because that is
what the captures record and what the tests compare against. The transport layer
converts at the boundary: it stages a full report before parsing, and hands back
everything after the ID when replying.

## Consequence

Including the ID in the reply put two on the wire. Parsing the stripped buffer
rejected every command as malformed, so the persona answered one register to
every read and ignored every move, while every codec test passed.

The fault is invisible from the codec's own tests. Only a capture of real traffic
showed it. Any stack this is ported to needs the same question asked: does it
hand over the payload with the report ID, or without.

## Revisit when

Porting to a stack whose HID layer passes reports through untouched. Then the
staging step is dead weight and can go, provided a wire capture confirms it.
