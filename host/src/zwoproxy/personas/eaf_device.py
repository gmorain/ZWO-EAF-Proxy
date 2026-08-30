"""Facedancer device presenting itself to an ASIAIR as a ZWO EAF.

Every descriptor value comes from `descriptors.py`, which holds the bytes the
real device sent in `captures/01-enumerate.pcap`. `test_descriptors.py` checks
what this class emits against those bytes.
"""

from __future__ import annotations

import logging

from facedancer import (
    USBConfiguration,
    USBDescriptor,
    USBDevice,
    USBDirection,
    USBEndpoint,
    USBInterface,
    USBTransferType,
    class_request_handler,
    to_this_interface,
    use_inner_classes_automatically,
)

from ..focuser import UNSUPPORTED, Focuser
from . import descriptors, protocol
from .eaf import (
    FIRMWARE_VERSION,
    PLACEHOLDER_SERIAL,
    USB_SERIAL_STRING,
    ZWO_EAF_PID,
    ZWO_VID,
    Register,
)

HID_DESCRIPTOR_TYPE = 0x21
HID_REPORT_DESCRIPTOR_TYPE = 0x22

HID_GET_REPORT = 0x01
HID_SET_REPORT = 0x09

log = logging.getLogger(__name__)


@use_inner_classes_automatically
class EAFDevice(USBDevice):
    """A ZWO EAF, as far as an ASIAIR can tell."""

    name: str = "ZWO EAF (emulated)"

    vendor_id: int = ZWO_VID
    product_id: int = ZWO_EAF_PID

    device_class: int = 0
    device_subclass: int = 0
    protocol_revision_number: int = 0
    max_packet_size_ep0: int = 64

    usb_spec_version: int = 0x0200
    device_revision: int = 0x0100

    manufacturer_string: str = "ZWO"
    product_string: str = "ZWO Device"
    serial_number_string: str = USB_SERIAL_STRING

    class Configuration(USBConfiguration):
        number: int = 1
        max_power: int = 100
        self_powered: bool = False
        supports_remote_wakeup: bool = True

        class Interface(USBInterface):
            number: int = 0
            class_number: int = 3
            subclass_number: int = 0
            protocol_number: int = 0

            class ReportEndpoint(USBEndpoint):
                """Declared, polled, and never used. It NAKs for the life of the
                connection, which is what the real device does; the protocol
                rides control transfers instead."""

                number: int = 1
                direction: USBDirection = USBDirection.IN
                transfer_type: USBTransferType = USBTransferType.INTERRUPT
                max_packet_size: int = 16
                interval: int = 10

            @class_request_handler(number=HID_SET_REPORT)
            @to_this_interface
            def handle_set_report(self, request):
                """The host's command channel. Feature report 3."""
                device = self.get_device()
                try:
                    command = protocol.parse_command(bytes(request.data))
                except protocol.MalformedReport as error:
                    log.warning("ignoring malformed report: %s", error)
                    request.ack()
                    return
                device.apply(command)
                request.ack()

            @class_request_handler(number=HID_GET_REPORT)
            @to_this_interface
            def handle_get_report(self, request):
                """The host's read channel. Feature report 1, and the host asks
                for 17 bytes against a 16-byte report."""
                device = self.get_device()
                request.reply(device.current_reply()[: request.length])

            class HIDDescriptor(USBDescriptor):
                number: int = 0
                type_number: int = HID_DESCRIPTOR_TYPE
                raw: bytes = descriptors.CONFIGURATION[18:27]
                include_in_config: bool = True

            class ReportDescriptor(USBDescriptor):
                number: int = 0
                type_number: int = HID_REPORT_DESCRIPTOR_TYPE
                raw: bytes = descriptors.REPORT

    #
    # Protocol state. The persona owns what to say; the focuser owns the truth.
    #

    focuser: Focuser = None
    serial: bytes = PLACEHOLDER_SERIAL
    fallback_celsius: float = 20.0
    firmware_version: tuple[int, int, int] = FIRMWARE_VERSION

    def __post_init__(self) -> None:
        super().__post_init__()
        self._pending = Register.STATE
        # Byte 9 of the state block. The host owns it; we only store it.
        self._settings = protocol.SETTINGS_BASE

    def apply(self, command: protocol.Command) -> None:
        """Act on one decoded command and remember what to answer next."""
        if isinstance(command, protocol.ReadRegister):
            self._pending = command.register
            log.info("read register %#04x", command.register)
            return

        self._pending = Register.STATE
        if command.settings is not None and command.settings != self._settings:
            log.info("settings byte %#04x -> %#04x", self._settings, command.settings)
            self._settings = command.settings
        if command.go:
            log.info("move to %d", command.position)
            self.focuser.move_to(command.position)
        elif command.sync:
            log.info("set position to %d", command.position)
            self.focuser.set_position(command.position)
        else:
            log.info("halt (host believed position %d)", command.position)
            self.focuser.halt()

    def current_reply(self) -> bytes:
        """The report the host reads back, for whichever register it last named."""
        register = self._pending
        if register == Register.STATE:
            centi = self.focuser.temperature()
            body = protocol.encode_state(
                moving=self.focuser.is_moving(),
                position=self.focuser.position(),
                celsius=self.fallback_celsius if centi == UNSUPPORTED else centi / 100,
                settings=self._settings,
            )
        elif register == Register.IDENTITY:
            body = protocol.identity_body(self.firmware_version)
        elif register == Register.SERIAL:
            body = protocol.serial_body(self.serial)
        elif register == Register.UNKNOWN_0D:
            body = protocol.zero_body()
        else:
            # No capture ever shows this device being asked for a register it does
            # not implement, so there is no observed refusal to copy. Answer the
            # way 0x0D does and say so loudly.
            log.warning("unobserved register %#04x, replying with a zero body", register)
            body = protocol.zero_body()
        return protocol.frame_reply(register, body)
