"""Decoder tests using the gateware's own test vectors.

The expected byte sequences are lifted from cynthion.gateware.analyzer.analyzer,
which asserts the analyzer emits exactly these.
"""

import pytest

from zwoproxy import capture


def test_start_event_vector():
    decoder = capture.StreamDecoder()
    records = list(decoder.feed(bytes([0xFF, 0x04, 0x00, 0x00])))
    assert len(records) == 1
    assert isinstance(records[0], capture.CapturedEvent)
    assert records[0].name == "CAPTURE_START_HIGH"
    assert records[0].timestamp == 0


def test_packet_vector():
    decoder = capture.StreamDecoder()
    stream = bytes([0x00, 0x0A, 0x00, 0x00]) + bytes(range(10))
    records = list(decoder.feed(stream))
    assert len(records) == 1
    assert isinstance(records[0], capture.CapturedPacket)
    assert records[0].data == bytes(range(10))


def test_split_across_feeds():
    decoder = capture.StreamDecoder()
    stream = bytes([0x00, 0x0A, 0x00, 0x00]) + bytes(range(10))
    assert list(decoder.feed(stream[:3])) == []
    records = list(decoder.feed(stream[3:]))
    assert len(records) == 1
    assert records[0].data == bytes(range(10))


def test_timestamp_wrap_is_extended():
    decoder = capture.StreamDecoder()
    list(decoder.feed(bytes([0x00, 0x00, 0xFF, 0xFF])))
    records = list(decoder.feed(bytes([0x00, 0x00, 0x00, 0x05])))
    assert records[0].timestamp == (1 << 16) + 5


def test_state_byte_never_touches_vbus_bits():
    for speed in capture.Speed:
        state = capture.STATE_ENABLE | (int(speed) << 1)
        assert state & 0b1111_1000 == 0, "VBUS/power bits must stay clear"


def test_odd_length_packet_is_word_padded():
    """The gateware ring buffer is 16-bit words, so odd packets carry a pad byte.

    Missing this desynchronises the whole stream: the pad is read as the high
    byte of the next length. Vector is a 3-byte SOF followed by an event.
    """
    decoder = capture.StreamDecoder()
    stream = bytes.fromhex("00030002a5063400") + bytes.fromhex("ff13ea30")
    records = list(decoder.feed(stream))
    assert len(records) == 2
    assert records[0].data == bytes.fromhex("a50634")
    assert isinstance(records[1], capture.CapturedEvent)
    assert records[1].name == "LINESTATE_FS_K"


def test_even_length_packet_has_no_pad():
    decoder = capture.StreamDecoder()
    stream = bytes.fromhex("00040002a5063401") + bytes.fromhex("ff13ea30")
    records = list(decoder.feed(stream))
    assert len(records) == 2
    assert records[0].data == bytes.fromhex("a5063401")


def test_implausible_length_raises_rather_than_emitting_garbage():
    decoder = capture.StreamDecoder()
    with pytest.raises(capture.StreamDesyncError):
        list(decoder.feed(bytes.fromhex("05ff0000") + bytes(2000)))
