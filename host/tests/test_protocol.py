"""Codec tests against bytes taken off the wire, plus malformed input.

Every hex string marked "captured" is a real report from `captures/`. If one of
these fails, the persona has diverged from the device it imitates.
"""

import pytest

from zwoproxy.personas import protocol
from zwoproxy.personas.eaf import Register


class TestCapturedCommands:
    """Commands the ASIAIR actually sent."""

    def test_read_identity(self):
        captured = bytes.fromhex("037e5a02040000000000000000000000")
        assert protocol.parse_command(captured) == protocol.ReadRegister(Register.IDENTITY)

    def test_read_state(self):
        captured = bytes.fromhex("037e5a02030000000000000000000000")
        assert protocol.parse_command(captured) == protocol.ReadRegister(Register.STATE)

    def test_read_serial(self):
        captured = bytes.fromhex("037e5a020c0000000000000000000000")
        assert protocol.parse_command(captured) == protocol.ReadRegister(Register.SERIAL)

    def test_move_to_17000(self):
        captured = bytes.fromhex("037e5a03" + "010000004268000000017530")
        assert protocol.parse_command(captured) == protocol.WriteState(
            go=True, position=17000, settings=protocol.SETTINGS_BASE
        )

    def test_halt_carries_a_stale_position(self):
        """The position in a halt is whatever the host last read. The device
        ignores it and stops where it is."""
        captured = bytes.fromhex("037e5a03" + "000000001df7000000017530")
        assert protocol.parse_command(captured) == protocol.WriteState(
            go=False, position=7671, settings=protocol.SETTINGS_BASE
        )


class TestCapturedReplies:
    def test_state_reply_is_reproduced_byte_for_byte(self):
        captured = bytes.fromhex("017e5a030000000003e8008052017530")
        body = protocol.encode_state(moving=False, position=1000, celsius=28.50)
        assert protocol.frame_reply(Register.STATE, body) == captured

    def test_identity_reply_is_reproduced_byte_for_byte(self):
        captured = bytes.fromhex("017e5a04030802454541464e00000000")
        assert protocol.frame_reply(Register.IDENTITY, protocol.identity_body()) == captured

    def test_temperature_round_trips_the_captured_values(self):
        for raw, celsius in ((0x8052, 28.50), (0x7FEE, 27.50), (0x811A, 30.50)):
            assert protocol.decode_temperature(raw) == celsius
            assert protocol.encode_temperature(celsius) == raw


class TestUntrustedInput:
    """The ASIAIR leaks uninitialised heap into padding, so nothing after the
    arguments a command defines can be trusted."""

    def test_junk_padding_is_ignored(self):
        """A real capture: a valid read of 0x04 followed by heap residue."""
        captured = bytes.fromhex("037e5a020400e09763223a22322e3022")
        assert protocol.parse_command(captured) == protocol.ReadRegister(Register.IDENTITY)

    def test_oversized_report_is_accepted_and_truncated(self):
        padded = bytes.fromhex("037e5a0204") + b"\xff" * 200
        assert protocol.parse_command(padded) == protocol.ReadRegister(Register.IDENTITY)

    @pytest.mark.parametrize(
        "data",
        [b"", b"\x03", b"\x03\x7e", b"\x03\x7e\x5a", b"\x03\x7e\x5a\x02"],
    )
    def test_truncated_reports_are_rejected(self, data):
        with pytest.raises(protocol.MalformedReport):
            protocol.parse_command(data)

    def test_bad_magic_is_rejected(self):
        with pytest.raises(protocol.MalformedReport):
            protocol.parse_command(bytes.fromhex("03dead02040000000000000000000000"))

    def test_wrong_report_id_is_rejected(self):
        with pytest.raises(protocol.MalformedReport):
            protocol.parse_command(bytes.fromhex("017e5a02040000000000000000000000"))

    def test_state_write_truncated_before_position_is_rejected(self):
        with pytest.raises(protocol.MalformedReport):
            protocol.parse_command(bytes.fromhex("037e5a030100"))

    def test_body_must_be_exactly_twelve_bytes(self):
        with pytest.raises(ValueError):
            protocol.frame_reply(Register.STATE, b"\x00" * 11)

    def test_position_beyond_u32_is_rejected(self):
        with pytest.raises(ValueError):
            protocol.encode_state(moving=False, position=1 << 32, celsius=20.0)

    def test_absurd_temperature_clamps_rather_than_overflowing(self):
        assert protocol.encode_temperature(1e9) == 0xFFFF
        assert protocol.encode_temperature(-1e9) == 0

    def test_serial_longer_than_a_body_is_rejected(self):
        with pytest.raises(ValueError):
            protocol.serial_body(b"\x00" * 13)


class TestPositionSync:
    """A write with go clear and the sync flag set redefines where the device is.
    Bytes from captures/15-zero-position.pcap, the real EAF zeroed from an ASIAIR
    while it sat at 5000."""

    def test_zero_is_a_sync_not_a_halt(self):
        captured = bytes.fromhex("037e5a03" + "000000000000010000017530")
        command = protocol.parse_command(captured)
        assert command == protocol.WriteState(
            go=False, position=0, sync=True, settings=protocol.SETTINGS_BASE
        )

    def test_sync_to_the_current_position_is_still_a_sync(self):
        """The device was at 5000 and told 5000, so nothing observable happened.
        Reading these as halts is what hid the meaning of the flag."""
        captured = bytes.fromhex("037e5a03" + "000000001388010000017530")
        command = protocol.parse_command(captured)
        assert command == protocol.WriteState(
            go=False, position=5000, sync=True, settings=protocol.SETTINGS_BASE
        )

    def test_a_halt_has_the_flag_clear(self):
        captured = bytes.fromhex("037e5a03" + "000000001df7000000017530")
        command = protocol.parse_command(captured)
        assert command == protocol.WriteState(
            go=False, position=7671, sync=False, settings=protocol.SETTINGS_BASE
        )

    def test_a_move_has_the_flag_clear(self):
        captured = bytes.fromhex("037e5a03" + "010000001388000000017530")
        command = protocol.parse_command(captured)
        assert command == protocol.WriteState(
            go=True, position=5000, sync=False, settings=protocol.SETTINGS_BASE
        )


class TestReverseSetting:
    """Body byte 9 carries the ASIAIR's Reverse toggle.

    Bytes from `captures/18-reverse.pcap`, where Reverse was switched on and
    then off with the focuser stationary. See docs/protocol/registers.md.
    """

    REVERSE_ON = bytes.fromhex("037e5a03000000001388000000037530")
    REVERSE_OFF = bytes.fromhex("037e5a03000000001388000000017530")
    REPLY_ON = bytes.fromhex("017e5a03000000001388007fee037530")

    def test_the_write_carries_the_reverse_bit(self):
        on = protocol.parse_command(self.REVERSE_ON)
        off = protocol.parse_command(self.REVERSE_OFF)
        assert on.settings & protocol.SETTINGS_REVERSE
        assert not off.settings & protocol.SETTINGS_REVERSE

    def test_the_toggle_write_is_otherwise_a_halt(self):
        """It carries go clear, sync clear, and the current position."""
        command = protocol.parse_command(self.REVERSE_ON)
        assert command.go is False
        assert command.sync is False
        assert command.position == 5000

    def test_a_reply_echoes_the_settings_byte(self):
        body = protocol.encode_state(
            moving=False,
            position=5000,
            celsius=27.50,
            settings=protocol.SETTINGS_BASE | protocol.SETTINGS_REVERSE,
        )
        assert protocol.frame_reply(0x03, body) == self.REPLY_ON

    def test_a_short_report_reports_no_settings(self):
        """Truncated before byte 9, so there is nothing to store."""
        assert protocol.parse_command(bytes.fromhex("037e5a030000000013880000")).settings is None
