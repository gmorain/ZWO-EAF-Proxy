"""Device-type contract, mirroring firmware/main/include/focuser.h.

Kept in sync by hand, and `test_focuser_mirror.py` fails if the two drift. The
only intended difference is naming: snake_case here, camelCase there. Return
types and units are the same contract on both vehicles, and the test checks
them too.
"""

from typing import Protocol

UNSUPPORTED = -(2**31)
"""Returned by backends that cannot answer a query, mirroring `kUnsupported`.

The persona decides what to report upstream rather than the backend inventing a
value.
"""


class Focuser(Protocol):
    """A real focuser, as seen by a persona."""

    def begin(self) -> bool:
        """Open the hardware. False if it is not there."""

    def position(self) -> int:
        """Absolute step count."""

    def move_to(self, target: int) -> bool:
        """Absolute, non-blocking. False if the target was refused."""

    def halt(self) -> bool:
        """Must be immediate."""

    def set_position(self, position: int) -> bool:
        """Redefine the current position without moving.

        The host zeroes a focuser this way; see docs/protocol/registers.md.
        """

    def is_moving(self) -> bool: ...

    def max_step(self) -> int: ...

    def temperature(self) -> int:
        """Hundredths of a degree Celsius, or UNSUPPORTED."""

    def tick(self) -> None:
        """Drive the backend's own state machine. Called often."""
