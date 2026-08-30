"""The register dispatch: which register answers what, and what a write does.

This layer was silently wrong in the firmware once. Every codec test passed while
the persona answered register 0x03 to every read, because the fault was here.
"""

import pytest

from zwoproxy.backends.simulated import SimulatedFocuser
from zwoproxy.personas import protocol
from zwoproxy.personas.eaf import Register
from zwoproxy.personas.eaf_device import EAFDevice

SERIAL = bytes.fromhex("6000aabbccddeeff")


@pytest.fixture
def device():
    focuser = SimulatedFocuser(position=3000, steps_per_second=1000, celsius=21.5)
    return EAFDevice(focuser=focuser, serial=SERIAL, fallback_celsius=20.0)


def read(register: int) -> protocol.ReadRegister:
    return protocol.ReadRegister(register=register)


class TestEachRegisterAnswersItself:
    def test_identity(self, device):
        device.apply(read(Register.IDENTITY))
        assert device.current_reply().hex() == "017e5a04030802454541464e00000000"

    def test_serial(self, device):
        device.apply(read(Register.SERIAL))
        assert device.current_reply().hex() == "017e5a0c6000aabbccddeeff00000000"

    def test_state(self, device):
        device.apply(read(Register.STATE))
        assert device.current_reply().hex() == "017e5a03000000000bb8007d96017530"

    def test_0d_is_a_zero_body(self, device):
        device.apply(read(Register.UNKNOWN_0D))
        assert device.current_reply().hex() == "017e5a0d000000000000000000000000"

    def test_unobserved_register_echoes_itself_with_a_zero_body(self, device):
        """No capture shows the device refusing a register, so there is no
        observed refusal to imitate."""
        device.apply(read(0x77))
        assert device.current_reply().hex() == "017e5a77000000000000000000000000"


class TestWrites:
    def test_move_reaches_the_focuser(self, device):
        device.apply(protocol.WriteState(go=True, position=15000))
        assert device.focuser.is_moving()

    def test_a_write_leaves_state_pending(self, device):
        device.apply(read(Register.IDENTITY))
        device.apply(protocol.WriteState(go=True, position=15000))
        assert device.current_reply()[3] == Register.STATE

    def test_halt_ignores_the_position_it_carries(self, device):
        device.apply(protocol.WriteState(go=True, position=15000))
        device.apply(protocol.WriteState(go=False, position=1))
        assert not device.focuser.is_moving()
        assert device.focuser.position() != 1


def test_unsupported_temperature_uses_the_fallback():
    focuser = SimulatedFocuser(position=0, celsius=None)
    device = EAFDevice(focuser=focuser, serial=SERIAL, fallback_celsius=20.0)
    device.apply(read(Register.STATE))
    raw = int.from_bytes(device.current_reply()[11:13], "big")
    assert protocol.decode_temperature(raw) == 20.0


class TestSyncReachesTheFocuser:
    def test_zero_redefines_position_without_moving(self, device):
        device.apply(protocol.WriteState(go=False, position=0, sync=True))
        assert device.focuser.position() == 0
        assert not device.focuser.is_moving()

    def test_sync_is_not_a_halt(self, device):
        """Discarding the position here leaves the focuser holding old
        coordinates while the host believes it was zeroed."""
        device.apply(protocol.WriteState(go=False, position=1234, sync=True))
        assert device.focuser.position() == 1234


def test_the_reverse_setting_survives_into_the_reply():
    """The host owns byte 9; the device stores it and echoes it back.

    Emitting a constant instead makes the ASIAIR's Reverse toggle appear to
    never take. See captures/18-reverse.pcap.
    """
    focuser = SimulatedFocuser(position=5000, celsius=27.5)
    device = EAFDevice(focuser=focuser, serial=SERIAL, fallback_celsius=20.0)

    device.apply(read(Register.STATE))
    assert device.current_reply()[13] == protocol.SETTINGS_BASE

    turned_on = protocol.SETTINGS_BASE | protocol.SETTINGS_REVERSE
    device.apply(protocol.WriteState(go=False, position=5000, settings=turned_on))
    assert device.current_reply()[13] == turned_on

    device.apply(protocol.WriteState(go=False, position=5000, settings=protocol.SETTINGS_BASE))
    assert device.current_reply()[13] == protocol.SETTINGS_BASE
