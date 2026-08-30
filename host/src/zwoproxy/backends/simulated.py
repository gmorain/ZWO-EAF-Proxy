"""A focuser that exists only in memory.

Lets the persona be exercised with no hardware attached. It moves at a fixed
step rate so an ASIAIR sees position changing over time, and it can be halted
part way.
"""

from __future__ import annotations

import time

from ..focuser import UNSUPPORTED


class SimulatedFocuser:
    """Implements `Focuser`. Movement is integrated from the wall clock."""

    def __init__(
        self,
        *,
        position: int = 0,
        steps_per_second: float = 500.0,
        celsius: float | None = 20.0,
    ) -> None:
        if steps_per_second <= 0:
            raise ValueError("steps_per_second must be positive")
        self._position = float(position)
        self._target = position
        self._rate = steps_per_second
        # The interface reports hundredths of a degree; the constructor takes
        # degrees because that is what the CLI and the tests speak.
        self._temperature_centi = UNSUPPORTED if celsius is None else round(celsius * 100)
        self._last = time.monotonic()

    def _advance(self) -> None:
        now = time.monotonic()
        elapsed, self._last = now - self._last, now
        remaining = self._target - self._position
        if remaining == 0:
            return
        step = self._rate * elapsed
        if abs(remaining) <= step:
            self._position = float(self._target)
        else:
            self._position += step if remaining > 0 else -step

    def begin(self) -> bool:
        """Nothing to open."""
        return True

    def position(self) -> int:
        self._advance()
        return int(self._position)

    def move_to(self, target: int) -> bool:
        if target < 0:
            return False
        self._advance()
        self._target = target
        return True

    def halt(self) -> bool:
        """Stop where we are.

        The real EAF overshoots its own halt by up to 353 steps and the ASIAIR
        accepts it, so stopping exactly is well inside tolerance.
        """
        self._advance()
        self._target = int(self._position)
        return True

    def set_position(self, position: int) -> bool:
        """Redefine where we are. No travel."""
        if position < 0:
            return False
        self._advance()
        self._position = float(position)
        self._target = position
        return True

    def is_moving(self) -> bool:
        self._advance()
        return int(self._position) != self._target

    def max_step(self) -> int:
        """No limit field appears in any capture, and the real device accepted a
        target of 17000 against a manual claiming 5760 steps."""
        return 0x7FFFFFFF

    def temperature(self) -> int:
        return self._temperature_centi

    def tick(self) -> None:
        """Travel is integrated from the clock on every query, so this only
        keeps the interface honest."""
        self._advance()
