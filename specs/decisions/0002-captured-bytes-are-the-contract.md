# 0002 — Captured bytes are the contract, on every vehicle

## Context

The device being emulated is not publicly documented. Everything known about it
was read off USB captures of the real hardware. Two independent implementations
exist, on different languages and stacks, and both must present the same bytes to
be accepted.

## Choice

The captured bytes are stored verbatim as the reference: descriptors as raw
arrays rather than rebuilt from helper libraries, and reference hex strings
duplicated deliberately in both test suites.

Every vehicle asserts against that reference. The tests compare emitted
descriptors and replies byte for byte with what the real device sent, and run on
the build host with no hardware attached.

## Consequence

Drift between the two implementations, or away from the real device, fails a test
rather than surviving to a capture session. Descriptor builders that produce
"equivalent" output are rejected: equivalent is not identical, and the host may
notice the difference.

The cost is that the reference is duplicated, and a genuine protocol correction
has to be applied in more than one place. That is deliberate. The captures are
the authority, and both copies are checked against them.

## Revisit when

The device's protocol is documented by its vendor, or a capture proves a field is
a range rather than a constant. Then that field can be generated instead of
frozen, and the reference narrowed to what is genuinely fixed.
