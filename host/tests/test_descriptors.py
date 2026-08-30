"""The persona must present exactly what the real EAF presented.

Reference bytes are in `personas/descriptors.py`, lifted from
`captures/01-enumerate.pcap`. If one of these fails, the persona changed. Fix the
persona, not the reference.
"""

from pathlib import Path

from zwoproxy.personas import descriptors as ref
from zwoproxy.personas import eaf_device
from zwoproxy.personas.eaf_device import EAFDevice


def test_device_descriptor_matches_the_capture():
    assert bytes(EAFDevice().get_descriptor()) == ref.DEVICE


def test_configuration_descriptor_matches_the_capture():
    device = EAFDevice()
    assert bytes(device.configurations[1].get_descriptor()) == ref.CONFIGURATION


def test_report_descriptor_is_the_captured_68_bytes():
    assert len(ref.REPORT) == 68
    interface = EAFDevice().configurations[1].interfaces[(0, 0)]
    report = interface.requestable_descriptors[(0x22, 0)]
    assert bytes(report.raw) == ref.REPORT


def test_hid_descriptor_length_agrees_with_the_report_descriptor():
    """A mismatch here makes a host ask for the wrong number of bytes."""
    hid = ref.CONFIGURATION[18:27]
    assert int.from_bytes(hid[7:9], "little") == len(ref.REPORT)


def test_interrupt_endpoint_is_declared_but_unused():
    """The real device declares 0x81 and NAKs it forever. Declaring it wrong
    would change enumeration; answering it would diverge from every capture."""
    endpoints = EAFDevice().configurations[1].interfaces[(0, 0)].endpoints
    assert list(endpoints) == [0x81]
    endpoint = endpoints[0x81]
    assert endpoint.max_packet_size == 16
    assert endpoint.interval == 10


class TestBehavioursTheRealDeviceHas:
    """Two things the genuine EAF does that a persona could accidentally not do.
    Both were inherited from Facedancer defaults before being asserted here."""

    def test_no_device_qualifier_is_offered(self):
        """The real device STALLs GET_DESCRIPTOR(DEVICE_QUALIFIER), three times
        per enumeration, and the ASIAIR proceeds. Answering it would advertise
        high speed; the link is full speed."""
        device = EAFDevice()
        offered = {int(key) for key in device.requestable_descriptors}
        assert 6 not in offered, "a device qualifier would be answered instead of stalled"

    def test_the_interrupt_endpoint_is_never_written(self):
        """Endpoint 0x81 is declared and polled about 125 times a second, and the
        real device NAKs every one. All protocol rides control transfers."""
        source = Path(eaf_device.__file__).read_text()
        for writer in ("send_on_endpoint", "send", "write"):
            assert f".{writer}(" not in source, f"persona writes to an endpoint via {writer}"
