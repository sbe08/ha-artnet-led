import uuid
from socket import socket

from _socket import SO_BROADCAST, AF_INET, SOCK_DGRAM, SOL_SOCKET, SO_REUSEADDR, IPPROTO_UDP, inet_aton
from sortedcontainers import SortedDict

from custom_components.artnet_led.client import OpCode, ArtBase, ArtPoll, ArtPollReply, PortAddress, IndicatorState, \
    PortAddressProgrammingAuthority, BootProcess, NodeReport, Port, PortType, StyleCode, FailsafeState

ARTNET_PORT = 0x1936
HA_OEM = 0x2BE9

HA_ESTA = 0x0  # TODO
RDM_SUPPORT = False  # TODO
SWITCH_TO_SACN_SUPPORT = False  # TODO
ART_ADDRESS_SUPPORT = False  # TODO


class ArtNetServer:
    def __init__(self, firmware_version: int = 0, oem: int = 0, esta=0, short_name: str = "PyArtNet",
                 long_name: str = "Python ArtNet Server", is_server_dhcp_configured: bool = True):
        self.firmware_version = firmware_version
        self.oem = oem
        self.esta = esta
        self.short_name = short_name
        self.long_name = long_name
        self.dhcp_configured = is_server_dhcp_configured

        self.port_addresses = SortedDict()
        self.node_subscribers = set()

        # Spec calls this ArtPollResponse, but since that isn't defined, we'll use it to count ArtPollReply
        self.indicator_state = IndicatorState.LOCATE_IDENTIFY
        self.node_report = NodeReport.RC_POWER_OK
        self.status_message = "Starting ArtNet server..."
        self.art_poll_reply_counter = 0

        self.mac = uuid.getnode().to_bytes(6, "big")

    def add_port(self, port_address: PortAddress):
        port = Port(input=True, output=True, type=PortType.ART_NET,
                    sw_in=port_address.universe, sw_out=port_address.universe)

        self.port_addresses[port_address] = port
        self.update_subscribers()

    def remove_port(self, port_address: PortAddress):
        del self.port_addresses[port_address]
        self.update_subscribers()

    def update_subscribers(self):
        print()
        # TODO

    def get_grouped_ports(self):
        # Sort the ports by their net and subnet
        net_sub = set(map(lambda p: (p.net, p.sub_net), self.port_addresses))
        grouped_list = [
            [
                ns[0],
                ns[1],
                [p.universe for p in self.port_addresses if (p.net, p.sub_net) == ns]
            ]
            for ns in net_sub
        ]

        for gli in grouped_list:
            # Chunk the universes into lists of at most 4
            chunked_universes = [gli[2][i:i + 4] for i in range(0, len(gli[2]), 4)]

            # Put the Port as value, instead of just universe number
            gli[2] = [
                list(map(lambda u: self.port_addresses[PortAddress(gli[0], gli[1], u)], chunked_universe))
                for chunked_universe in chunked_universes
            ]

        return grouped_list

    def start_server(self):
        with socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP) as s:
            s.setsockopt(SOL_SOCKET, SO_BROADCAST, 1)
            s.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)

            s.bind(('', ARTNET_PORT))

            while True:
                data, addr = s.recvfrom(1024)

                data = bytearray(data)
                opcode = ArtBase.peek_opcode(data)

                if opcode == OpCode.OP_POLL:
                    poll = ArtPoll()
                    poll.deserialize(data)

                    if not self.should_handle_ports(*poll.target_port_bounds):
                        continue

                    if poll.notify_on_change:
                        self.node_subscribers.add(addr)

                    own_ip_str = s.getsockname()[0]
                    print(f"Own IP address: {own_ip_str}")
                    own_ip = inet_aton(own_ip_str)

                    for (net, sub_net, ports_chunk) in self.get_grouped_ports():
                        for ports in ports_chunk:
                            node_report = self.node_report.report(self.art_poll_reply_counter, self.status_message)

                            poll_reply = ArtPollReply(
                                source_ip=own_ip, firmware_version=self.firmware_version, net_switch=net,
                                sub_switch=sub_net, oem=self.oem, indicator_state=IndicatorState.LOCATE_IDENTIFY,
                                port_address_programming_authority=PortAddressProgrammingAuthority.PROGRAMMATIC,
                                boot_process=BootProcess.FLASH, supports_rdm=RDM_SUPPORT, esta=0,
                                short_name=self.short_name, long_name=self.long_name, node_report=node_report,
                                ports=ports, style=StyleCode.ST_CONTROLLER, mac_address=self.mac,
                                supports_web_browser_configuration=True, dhcp_configured=self.dhcp_configured,
                                dhcp_capable=True, supports_15_bit_port_address=True,
                                supports_switching_to_sacn=SWITCH_TO_SACN_SUPPORT, squawking=RDM_SUPPORT,
                                supports_switching_of_output_style=ART_ADDRESS_SUPPORT,
                                supports_rdm_through_artnet=RDM_SUPPORT, failsafe_state=FailsafeState.HOLD_LAST_STATE
                            )

                            packet = poll_reply.serialize()

                            s.sendto(packet, (addr[0], ARTNET_PORT))

                            self.art_poll_reply_counter += 1

                    print(f"{opcode}: {data}")

                elif opcode == OpCode.OP_POLL_REPLY:
                    reply = ArtPollReply()
                    reply.deserialize(data)
                    print(f"{opcode}: {data}")

                elif opcode == OpCode.OP_SYNC:
                    print()

    #                 TODO set port.good_input.data_received

    def should_handle_ports(self, lower_port: PortAddress, upper_port: PortAddress) -> bool:
        if not self.port_addresses:
            return False

        lowest_port_listener = self.port_addresses.peekitem(0)[0]
        upper_port_listener = self.port_addresses.peekitem(-1)[0]

        return not (lower_port > upper_port_listener or upper_port < lowest_port_listener)


server = ArtNetServer(firmware_version=1, short_name="Test python", long_name="Hello I am testing ArtNet server")
server.add_port(PortAddress(0, 0, 0))
server.add_port(PortAddress(0, 0, 1))
server.start_server()
