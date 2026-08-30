"""Pinefeat CEF (Canon EF lens controller) dialect.

Line-oriented ASCII over USB CDC. Encoding and decoding are pure functions so
they can be unit tested without hardware and ported to C++ mechanically; the
caller supplies the transport.

Protocol read off the official ASCOM driver source, see docs/protocol/pinefeat.md
"""

OK = "ok"
ERROR = "er"
NOT_CONNECTED = "nc"

TERMINATOR = "\n"


class PinefeatError(RuntimeError):
    """The controller replied with an error status."""


def frame(command: str) -> bytes:
    """Wire form of a command."""
    return (command + TERMINATOR).encode("ascii")


def unframe(reply: bytes) -> str:
    """Strip framing from a reply read up to and including the terminator."""
    return reply.decode("ascii").rstrip("\r\n")


def check(reply: str) -> str:
    """Raise on an error status, otherwise pass the reply through."""
    if reply in (ERROR, NOT_CONNECTED):
        raise PinefeatError(reply)
    return reply


def move_to(target: int) -> str:
    """Absolute move. The driver clamps negatives to zero; match that."""
    return f"m{max(0, target)}"


def set_aperture(f_stop: float) -> str:
    """Aperture in f-stops. The driver formats invariant, up to 5 decimals."""
    return f"a{f_stop:.5f}".rstrip("0").rstrip(".")


GET_VERSION = "v"
GET_POSITION = "f"
IS_MOVING = "e"
GET_RANGE = "r"
CALIBRATE = "c"
GET_APERTURE_RANGE = "a"

# There is no halt command. See docs/protocol/pinefeat.md.
HALT: None = None


def parse_position(reply: str) -> int:
    return int(check(reply))


def parse_is_moving(reply: str) -> bool:
    return check(reply) == "y"


def parse_max_increment(reply: str) -> int:
    """Range comes back as ``<min>-<max>``; the driver takes the last field."""
    return int(check(reply).rsplit("-", 1)[-1])
