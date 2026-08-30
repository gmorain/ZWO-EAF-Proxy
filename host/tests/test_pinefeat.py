import pytest

from zwoproxy.backends import pinefeat


def test_framing_round_trip():
    assert pinefeat.frame("f") == b"f\n"
    assert pinefeat.unframe(b"1234\r\n") == "1234"


def test_move_clamps_negative():
    assert pinefeat.move_to(5200) == "m5200"
    assert pinefeat.move_to(-1) == "m0"


def test_aperture_formatting():
    assert pinefeat.set_aperture(3.5) == "a3.5"
    assert pinefeat.set_aperture(4.0) == "a4"


def test_error_statuses_raise():
    for status in (pinefeat.ERROR, pinefeat.NOT_CONNECTED):
        with pytest.raises(pinefeat.PinefeatError):
            pinefeat.check(status)


def test_parsers():
    assert pinefeat.parse_position("1234") == 1234
    assert pinefeat.parse_is_moving("y") is True
    assert pinefeat.parse_is_moving("n") is False
    assert pinefeat.parse_max_increment("0-9999") == 9999
