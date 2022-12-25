from dataclasses import dataclass
from enum import Enum

CLIENT_VERSION = 1

PROTOCOL_VERSION = 0x000E
PORT = 0x1936
HOME_ASSISTANT_ESTA = map(ord, "HA")


class OpCode(Enum):
    # @formatter:off
    OP_POLL                 = 0x2000
    OP_POLL_REPLY           = 0x2100
    OP_DIAG_DATA            = 0x2300
    OP_COMMAND              = 0x2400
    OP_OUTOUT               = 0x5000
    OP_NZS                  = 0x5100
    OP_SYNC                 = 0x5200
    OP_ADDRESS              = 0x6000
    OP_INPUT                = 0x7000
    OP_TOD_REQUEST          = 0x8000
    OP_TOD_DATA             = 0x8100
    OP_TOD_CONTROL          = 0x8200
    OP_RDM                  = 0x8300
    OP_RDM_SUB              = 0x8400
    OP_VIDEO_SETUP          = 0xA010
    OP_VIDEO_PALETTE        = 0xA020
    OP_VIDEO_DATA           = 0xA040
    OP_MAC_MASTER           = 0xF000
    OP_MAC_SLAVE            = 0xF100
    OP_FIRMWARE_MASTER      = 0xF200
    OP_FIRMWARE_REPLY       = 0xF300
    OP_FILE_TN_MASTER       = 0xF400
    OP_FILE_FN_MASTER       = 0xF500
    OP_FILE_FN_REPLY        = 0xF600
    OP_IP_PROG              = 0xF800
    OP_IP_PROG_REPLY        = 0xF900
    OP_MEDIA                = 0x9000
    OP_MEDIA_PATCH          = 0x9100
    OP_MEDIA_CONTROL        = 0x9200
    OP_MEDIA_CONTROL_REPLY  = 0x9300
    OP_TIME_CODE            = 0x9700
    OP_TIME_SYNC            = 0x9800
    OP_TRIGGER              = 0x9900
    OP_DIRECTORY            = 0x9A00
    OP_DIRECTORY_REPLY      = 0x9B00
    # @formatter:on


class DiagnosticsMode(Enum):
    UNICAST = False
    BROADCAST = True


class DiagnosticsPriority(Enum):
    # @formatter:off
    DP_LOW      = 0x10
    DP_MED      = 0x40
    DP_HIGH     = 0x80
    DP_CRITICAL = 0xE0
    DP_VOLATILE = 0xF0
    # @formatter:on


class NodeReport(Enum):
    # @formatter:off
    RC_DEBUG            = (0x0000, "Booted in debug mode (Only used in development)")
    RC_POWER_OK         = (0x0001, "Power On Tests successful")
    RC_POWER_FAIL       = (0x0002, "Hardware tests failed at Power On")
    RC_SOCKET_WR1       = (0x0003, "Last UDP from Node failed due to truncated length, \
                                    Most likely caused by a collision.")
    RC_PARSE_FAIL       = (0x0004, "Unable to identify last UDP transmission. Check OpCode and packet length.")
    RC_UDP_FAIL         = (0x0005, "Unable to open Udp Socket in last transmission attempt")
    RC_SH_NAME_OK       = (0x0006, "Confirms that Short Name programming via ArtAddress, was successful.")
    RC_LO_NAME_OK       = (0x0007, "Confirms that Long Name programming via ArtAddress, was successful.")
    RC_DMX_ERROR        = (0x0008, "DMX512 receive errors detected.")
    RC_DMX_UDP_FULL     = (0x0009, "Ran out of internal DMX transmit buffers.")
    RC_DMX_RX_FULL      = (0x000A, "Ran out of internal DMX Rx buffers.")
    RC_SWITCH_ERR       = (0x000B, "Rx Universe switches conflict.")
    RC_CONFIG_ERR       = (0x000C, "Product configuration does not match firmware.")
    RC_DMX_SHORT        = (0x000D, "DMX output short detected. See GoodOutput field.")
    RC_FIRMWARE_FAIL    = (0x000E, "Last attempt to upload new firmware failed.")
    RC_USER_FAIL        = (0x000F, "User changed switch settings when address locked by remote programming.\
                                    User changes ignored.")
    RC_FACTORY_RES      = (0x0010, "Factory reset has occurred.")
    # @formatter:on


class StyleCode(Enum):
    # @formatter:off
    ST_NODE         = (0x00, "A DMX to / from Art-Net device")
    ST_CONTROLLER   = (0x01, "A lighting console.")
    ST_MEDIA        = (0x02, "A Media Server.")
    ST_ROUTE        = (0x03, "A network routing device.")
    ST_BACKUP       = (0x04, "A backup device.")
    ST_CONFIG       = (0x05, "A configuration or diagnostic tool.")
    ST_VISUAL       = (0x06, "A visualiser.")
    # @formatter:on


class PortAddress:
    def __init__(self, net: int, sub_net: int, universe: int = 0) -> None:
        super().__init__()
        assert (0 <= net <= 0xF)
        assert (0 <= sub_net <= 0xF)
        assert (0 <= universe <= 0x1FF)
        self._net = net
        self._sub_net = sub_net
        self._universe = universe

    @property
    def net(self):
        return self._net

    @net.setter
    def net(self, net):
        self._net = net

    @property
    def sub_net(self):
        return self._sub_net

    @sub_net.setter
    def sub_net(self, sub_net):
        self._sub_net = sub_net

    @property
    def universe(self):
        return self._universe

    @universe.setter
    def universe(self, universe):
        self._universe = universe

    @property
    def port_address(self):
        return (self.net << 13) + (self.sub_net << 9) + self.universe

    @port_address.setter
    def port_address(self, port_address):
        self._net = port_address >> 13 & 0xF
        self._sub_net = port_address >> 9 & 0xF
        self._universe = port_address & 0x1FF


class IndicatorState(Enum):
    # @formatter:off
    UNKNOWN         = 0
    LOCATE_IDENTITY = 1
    MUTE_MODE       = 2
    NORMAL_MODE     = 3
    # @formatter:on


class PortAddressProgrammingAuthority(Enum):
    # @formatter:off
    UNKNOWN         = 0
    FRONT_PANEL     = 1
    PROGRAMMATIC    = 2
    # @formatter:on


class BootProcess(Enum):
    FLASH = False
    ROM = True


class PortType(Enum):
    DMX512 = 0
    MIDI = 1
    AVAB = 2
    COLORTRAN_CMX = 3
    ADB_65_2 = 4
    ART_NET = 5
    DALI = 6


@dataclass
class GoodInput:
    data_received = False
    includes_dmx512_test_packets = False
    includes_dmx512_sips = False
    includes_dmx512_text_packets = False
    input_disabled = False
    receive_errors_detected = False

    @property
    def flags(self):
        return (self.data_received << 7) \
               + (self.includes_dmx512_test_packets << 6) \
               + (self.includes_dmx512_sips << 5) \
               + (self.includes_dmx512_text_packets << 4) \
               + (self.input_disabled << 3) \
               + (self.receive_errors_detected << 2)

    @flags.setter
    def flags(self, flags):
        self.data_received = bool(flags >> 7 & 1)
        self.includes_dmx512_test_packets = bool(flags >> 6 & 1)
        self.includes_dmx512_sips = bool(flags >> 5 & 1)
        self.includes_dmx512_text_packets = bool(flags >> 4 & 1)
        self.input_disabled = bool(flags >> 3 & 1)
        self.receive_errors_detected = bool(flags >> 2 & 1)


@dataclass
class GoodOutputA:
    data_being_transmitted = False
    includes_dmx512_test_packets = False
    includes_dmx512_sips = False
    includes_dmx512_text_packets = False
    merging_enabled = False
    short_detected = False
    merge_is_ltp = False
    use_sacn = False

    @property
    def flags(self):
        return (self.data_being_transmitted << 7) \
               + (self.includes_dmx512_test_packets << 6) \
               + (self.includes_dmx512_sips << 5) \
               + (self.includes_dmx512_text_packets << 4) \
               + (self.merging_enabled << 3) \
               + (self.short_detected << 2) \
               + (self.merge_is_ltp << 1) \
               + self.use_sacn

    @flags.setter
    def flags(self, flags):
        self.data_being_transmitted = bool(flags >> 7 & 1)
        self.includes_dmx512_test_packets = bool(flags >> 6 & 1)
        self.includes_dmx512_sips = bool(flags >> 5 & 1)
        self.includes_dmx512_text_packets = bool(flags >> 4 & 1)
        self.merging_enabled = bool(flags >> 3 & 1)
        self.short_detected = bool(flags >> 2 & 1)
        self.merge_is_ltp = bool(flags >> 1 & 1)
        self.use_sacn = bool(flags & 1)


@dataclass(init=True)
class Port:
    input = False
    output = False
    type = PortType.DMX512
    good_input = GoodInput()
    good_output_a = GoodOutputA()
    sw_in = 0
    sw_out = 0
    rdm_enabled = False
    output_continuous = False

    @property
    def port_types_flags(self) -> int:
        return (self.output << 7) \
               + (self.input << 6) \
               + self.type.value

    @port_types_flags.setter
    def port_types_flags(self, flags):
        self.output = bool(flags >> 7 & 1)
        self.input = bool(flags >> 6 & 1)
        self.type = PortType(flags & 0b11_1111)

    @property
    def good_output_b(self) -> int:
        return (self.rdm_enabled << 7) \
               + (self.output_continuous << 6)

    @good_output_b.setter
    def good_output_b(self, flags):
        self.rdm_enabled = bool(flags >> 7 & 1)
        self.output_continuous = bool(flags >> 6 & 1)


class FailsafeState(Enum):
    HOLD_LAST_STATE = 0
    ALL_OUTPUTS_0 = 1
    ALL_OUTPUTS_FULL = 2
    PLAYBACK_FAIL_SAFE_SCENE = 3


class ArtBase:
    def __init__(self, opcode: OpCode) -> None:
        super().__init__()
        self.__opcode = opcode

    def serialize(self) -> bytearray:
        packet = bytearray()
        packet.extend(map(ord, "Art-Net\0"))
        self._append_int_lsb(packet, self.__opcode.value)
        return packet

    def deserialize(self, packet: bytearray) -> int:
        packet_header, index = self._consume_str(packet, 0, 8)
        if packet_header != "Art-Net":
            raise SerializationException(f"Not a valid packet, expected \"Art-Net\", but is \"{packet_header}\"")

        opcode, index = self._consume_int_lsb(packet, index)
        if opcode != self.__opcode.value:
            raise SerializationException(f"Expected this packet to have opcode {self.__opcode}, but was {opcode}")

        return index

    @staticmethod
    def _pop(packet: bytearray, index: int) -> (int, int):
        return packet[index], index + 1

    @staticmethod
    def _append_int_lsb(packet: bytearray, number: int):
        packet.append(number & 0xFF)
        packet.append(number >> 8 & 0xFF)

    @staticmethod
    def _append_int_msb(packet: bytearray, number: int):
        packet.append(number >> 8 & 0xFF)
        packet.append(number & 0xFF)

    @staticmethod
    def _consume_int_lsb(packet: bytearray, index: int) -> (int, int):
        [lsb, msb] = packet[index:index + 2]
        return msb << 8 + lsb, index + 2

    @staticmethod
    def _consume_int_msb(packet: bytearray, index: int) -> (int, int):
        [msb, lsb] = packet[index:index + 2]
        return msb << 8 + lsb, index + 2

    @staticmethod
    def _consume_hex_number_lsb(packet: bytearray, index: int) -> (int, int):
        lower = hex(packet[index])[2:].zfill(2)
        upper = hex(packet[index + 1])[2:].zfill(2)
        return int(upper + lower, 16), index + 2

    @staticmethod
    def _consume_hex_number_msb(packet: bytearray, index: int) -> (int, int):
        upper = hex(packet[index])[2:].zfill(2)
        lower = hex(packet[index + 1])[2:].zfill(2)
        return int(upper + lower, 16), index + 2

    @staticmethod
    def _append_str(packet: bytearray, text: str, length: int):
        cut_text: str = text[:length - 1]
        padded_text = cut_text.ljust(length, '\0')
        packet.extend(map(ord, padded_text))

    @staticmethod
    def _consume_str(packet: bytearray, index: int, length: int) -> (str, int):
        str_bytes = str(packet[index:index + length - 1], "ASCII")
        string = str_bytes.split('\0')[0]
        return string, index + length

    @staticmethod
    def peek_opcode(packet: bytearray) -> OpCode | None:
        if len(packet) < 9:
            return None

        header = packet[0:8]
        if header != b'Art-Net\x00':
            return None

        opcode = ArtBase._consume_int_lsb(packet, 8)
        return OpCode(opcode[0])


class ArtPoll(ArtBase):

    def __init__(self,
                 protocol_version=PROTOCOL_VERSION,
                 enable_vlc_transmission: bool = False,
                 notify_on_change: bool = False,
                 ) -> None:
        super().__init__(OpCode.OP_POLL)
        self.__protocol_version = protocol_version
        self.__enable_vlc_transmission = enable_vlc_transmission
        self.__notify_on_change = notify_on_change

        self.__enable_diagnostics = False
        self.__diag_priority = DiagnosticsPriority.DP_LOW
        self.__diag_mode = DiagnosticsMode.BROADCAST

        self.__enable_targeted_mode = False
        self.__target_port_bottom: PortAddress = PortAddress(0x0, 0x0, 0x0)
        self.__target_port_top: PortAddress = PortAddress(0xF, 0xF, 0x199)

    def enable_diagnostics(self,
                           mode: DiagnosticsMode = DiagnosticsMode.BROADCAST,
                           diag_priority: DiagnosticsPriority = DiagnosticsPriority.DP_LOW
                           ):
        self.__enable_diagnostics = True
        self.__diag_priority = diag_priority
        self.__diag_mode = mode

    def enable_targeted_mode(self, target_port_bottom: PortAddress, target_port_top: PortAddress):
        self.__enable_targeted_mode = True
        self.__target_port_bottom = target_port_bottom
        self.__target_port_top: target_port_top

    @property
    def protocol_verison(self):
        return self.__protocol_version

    @property
    def vlc_transmission_enabled(self):
        return self.__enable_vlc_transmission

    @property
    def notify_on_change(self):
        return self.__notify_on_change

    @property
    def diagnostics_enabled(self):
        return self.__enable_diagnostics

    @property
    def diagnostics_priority(self):
        return self.__diag_priority

    @property
    def diagnostics_mode(self):
        return self.__diag_mode

    @property
    def targeted_mode_enabled(self):
        return self.__enable_targeted_mode

    @property
    def target_port_bounds(self):
        return self.__target_port_bottom, self.__target_port_top

    def serialize(self) -> bytearray:
        packet = super().serialize()
        self._append_int_msb(packet, self.__protocol_version)

        flags = (self.__enable_targeted_mode << 5) \
                + (self.__enable_vlc_transmission << 4) \
                + (self.__diag_mode.value << 3) \
                + (self.__enable_diagnostics << 2) \
                + (self.__notify_on_change << 1)

        packet.append(flags)
        packet.append(self.__diag_priority.value)
        self._append_int_msb(packet, self.__target_port_top.port_address)
        self._append_int_msb(packet, self.__target_port_bottom.port_address)
        return packet

    def deserialize(self, packet: bytearray) -> int:
        index = super().deserialize(packet)
        self.__protocol_version, index = self._consume_int_msb(packet, index)

        flags, index = self._pop(packet, index)
        self.__enable_targeted_mode = bool(flags >> 5 & 1)
        self.__enable_vlc_transmission = bool(flags >> 4 & 1)
        self.__diag_mode = DiagnosticsMode(bool(flags >> 3 & 1))
        self.__enable_diagnostics = bool(flags >> 2 & 1)
        self.__notify_on_change = bool(flags >> 1 & 1)

        self.__diag_priority = DiagnosticsPriority(packet[index])
        index += 1

        self.__target_port_top.port_address, index = self._consume_int_msb(packet, index)
        self.__target_port_bottom.port_address, index = self._consume_int_msb(packet, index)
        return index


class ArtPollReply(ArtBase):
    def __init__(self,
                 source_ip: bytearray = bytearray([0] * 4),
                 firmware_version: int = 14,
                 net__sub_net: PortAddress = PortAddress(0, 0),
                 oem: int = 0,
                 indicator_state: IndicatorState = IndicatorState.UNKNOWN,
                 port_address_programming_authority: PortAddressProgrammingAuthority = PortAddressProgrammingAuthority.UNKNOWN,
                 boot_process: BootProcess = BootProcess.ROM,
                 supports_rdm: bool = False,
                 esta: int = 0,
                 short_name: str = "Default short name",
                 long_name: str = "Default long name",
                 node_report: str = "",
                 ports: list[Port] = [],
                 acn_priority: int = 100,
                 sw_macro_bitmap: int = 0,
                 sw_remote_bitmap: int = 0,
                 style: StyleCode = StyleCode.ST_CONTROLLER,
                 mac_address: bytearray = bytearray([0] * 6),
                 bind_ip: bytearray = bytearray([0] * 4),
                 bind_index: int = 0,
                 supports_web_browser_configuration: bool = False,
                 dhcp_configured: bool = False,
                 dhcp_capable: bool = False,
                 supports_15_bit_port_address: bool = False,
                 supports_switching_to_sacn: bool = False,
                 squawking: bool = False,
                 supports_switching_of_output_style: bool = False,
                 supports_rdm_through_artnet: bool = False,
                 failsafe_state: FailsafeState = FailsafeState.HOLD_LAST_STATE,
                 supports_failover: bool = False,
                 supports_switching_port_direction: bool = False
                 ) -> None:
        super().__init__(opcode=OpCode.OP_POLL_REPLY)

        assert source_ip.__len__() == 4
        self.source_ip = source_ip
        self.port = PORT
        self.firmware_version = firmware_version
        self.net__sub_net = net__sub_net
        self.oem = oem
        self.indicator_state = indicator_state
        self.port_address_programming_authority = port_address_programming_authority
        self.boot_process = boot_process
        self.supports_rdm = supports_rdm
        self.esta = esta
        self.short_name = short_name
        self.long_name = long_name
        self.node_report = node_report

        assert len(ports) <= 4
        self.ports = [Port()] * (4 - len(ports))

        self.acn_priority = acn_priority

        self.sw_macro_bitmap = sw_macro_bitmap
        self.sw_remote_bitmap = sw_remote_bitmap
        self.style = style

        assert len(mac_address) == 6
        self.mac_address = mac_address

        assert len(bind_ip) == 4
        self.bind_ip = bind_ip

        self.bind_index = bind_index

        self.supports_web_browser_configuration = supports_web_browser_configuration
        self.dhcp_configured = dhcp_configured
        self.dhcp_capable = dhcp_capable
        self.supports_15_bit_port_address = supports_15_bit_port_address
        self.supports_switching_to_sacn = supports_switching_to_sacn
        self.squawking = squawking
        self.supports_switching_of_output_style = supports_switching_of_output_style
        self.supports_rdm_through_artnet = supports_rdm_through_artnet

        self.failsafe_state = failsafe_state
        self.supports_failover = supports_failover
        self.supports_switching_port_direction = supports_switching_port_direction

        self.__ubea_present = False
        self.__ubea = 0

        self.__supports_llrp = True
        self.__default_resp_uid = [0x0] * 6

    @property
    def ubea(self) -> int | None:
        return self.__ubea if self.__ubea_present else None

    @ubea.setter
    def ubea(self, ubea: int):
        self.__ubea_present = True
        self.__ubea = ubea

    @property
    def default_resp_uid(self):
        return self.__default_resp_uid if self.__supports_llrp else None

    @default_resp_uid.setter
    def default_resp_uid(self, default_resp_uid: bytearray):
        assert len(default_resp_uid) == 6
        self.__supports_llrp = True
        self.__default_resp_uid = default_resp_uid

    def serialize(self) -> bytearray:
        package = super().serialize()
        package.extend(self.source_ip)

        port_str = hex(self.port)[2:]
        package.extend([int(port_str[2:4]), int(port_str[0:2])])

        self._append_int_lsb(package, self.port)
        self._append_int_msb(package, self.firmware_version)
        package.append(self.net__sub_net.net)
        package.append(self.net__sub_net.sub_net)
        self._append_int_msb(package, self.oem)
        package.append(self.ubea)

        status1 = (self.indicator_state.value << 6) \
                  + (self.port_address_programming_authority.value << 4) \
                  + (self.boot_process.value << 2) \
                  + (self.supports_rdm < 1) \
                  + self.__ubea_present
        package.append(status1)

        self._append_int_lsb(package, self.esta)
        self._append_str(package, self.short_name, 18)
        self._append_str(package, self.long_name, 64)
        self._append_str(package, self.node_report, 64)

        self._append_int_msb(package, len([p for p in self.ports if p.input or p.output]))
        package.extend([p.port_types_flags for p in self.ports])
        package.extend([p.good_input.flags for p in self.ports])
        package.extend([p.good_output_a.flags for p in self.ports])
        package.extend([p.sw_in for p in self.ports])
        package.extend([p.sw_out for p in self.ports])
        package.append(self.acn_priority)
        package.append(self.sw_macro_bitmap)
        package.append(self.sw_remote_bitmap)
        package.extend([0, 0, 0])
        package.append(self.style.value)
        package.extend(self.mac_address)
        package.extend(self.bind_ip)
        package.append(self.bind_index)

        status2 = self.supports_web_browser_configuration \
                  + (self.dhcp_configured << 1) \
                  + (self.dhcp_capable << 2) \
                  + (self.supports_15_bit_port_address << 3) \
                  + (self.supports_switching_to_sacn << 4) \
                  + (self.squawking << 5) \
                  + (self.supports_switching_of_output_style << 6) \
                  + (self.supports_rdm_through_artnet << 7)
        package.append(status2)

        package.extend(map(lambda p: p.good_output_b, self.ports))

        status3 = (self.failsafe_state.value << 6) \
                  + (self.supports_failover << 5) \
                  + (self.__supports_llrp << 4) \
                  + (self.supports_switching_port_direction < 3)
        package.append(status3)
        package.extend(self.default_resp_uid)

        package.extend([0x0] * 15)

        return package

    def deserialize(self, packet: bytearray) -> int:
        index = super().deserialize(packet)

        self.source_ip = packet[index:index + 4]
        index += 4

        self.port, index = self._consume_hex_number_lsb(packet, index)
        self.firmware_version, index = self._consume_hex_number_msb(packet, index)

        self.net__sub_net.net, index = self._pop(packet, index)
        self.net__sub_net.sub_net, index = self._pop(packet, index)
        self.oem, index = self._consume_hex_number_msb(packet, index)
        self.ubea, index = self._pop(packet, index)

        status1, index = self._pop(packet, index)
        self.indicator_state = IndicatorState(status1 >> 6 & 2)
        self.port_address_programming_authority = PortAddressProgrammingAuthority(status1 >> 4 & 2)
        self.boot_process = BootProcess(bool(status1 >> 2 & 1))
        self.supports_rdm = bool(status1 >> 1 & 1)
        self.__ubea_present = bool(status1 & 1)

        self.esta, index = self._consume_hex_number_lsb(packet, index)
        self.short_name, index = self._consume_str(packet, index, 18)
        self.long_name, index = self._consume_str(packet, index, 64)
        self.node_report, index = self._consume_str(packet, index, 64)

        # TODO use number of ports
        _, index = self._consume_hex_number_msb(packet, index)
        port_type_flags = packet[index: index + 4]
        good_input_flags = packet[index + 4: index + 8]
        good_output_a_flags = packet[index + 8: index + 12]
        sw_ins = packet[index + 12: index + 16]
        sw_outs = packet[index + 16: index + 20]
        index += 20

        self.acn_priority, index = self._pop(packet, index)  # Used to be SwVideo
        self.sw_macro_bitmap, index = self._pop(packet, index)
        self.sw_remote_bitmap, index = self._pop(packet, index)

        index += 3

        self.style, index = self._pop(packet, index)

        self.mac_address = packet[index:index + 6]
        index += 6

        self.bind_ip = packet[index:index + 4]
        index += 4

        self.bind_index, index = self._pop(packet, index)

        status2, index = self._pop(packet, index)
        self.supports_web_browser_configuration = bool(status2 & 1)
        self.dhcp_configured = bool(status2 >> 1 & 1)
        self.dhcp_capable = bool(status2 >> 2 & 1)
        self.supports_15_bit_port_address = bool(status2 >> 3 & 1)
        self.supports_switching_to_sacn = bool(status2 >> 4 & 1)
        self.squawking = bool(status2 >> 5 & 1)
        self.supports_switching_of_output_style = bool(status2 >> 6 & 1)
        self.supports_rdm_through_artnet = bool(status2 >> 7 & 1)

        good_output_b_flags = packet[index: index + 4]
        index += 4

        for i in range(0, 4):
            port = self.ports[i]
            port.port_types_flags = port_type_flags[i]
            port.good_input.flags = good_input_flags[i]
            port.good_output_a.flags = good_output_a_flags[i]
            port.sw_in = sw_ins[i]
            port.sw_out = sw_outs[i]
            port.good_output_b = good_output_b_flags[i]

        status3, index = self._pop(packet, index)
        self.failsafe_state = FailsafeState(status3 >> 6)
        self.supports_failover = bool(status3 >> 5 & 1)
        self.__supports_llrp = bool(status3 >> 4 & 1)
        self.supports_switching_port_direction = bool(status3 >> 3 & 1)

        self.default_resp_uid = packet[index:index + 6]
        index += 6

        index += 15
        return index

    # udp.port eq 6454 and ip.src != 192.168.1.104


class SerializationException(Exception):

    def __init__(self, *args: object) -> None:
        super().__init__(*args)
