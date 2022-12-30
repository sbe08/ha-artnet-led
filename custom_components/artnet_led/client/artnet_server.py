import asyncio
import uuid
from asyncio import transports
from dataclasses import dataclass
from datetime import time
from socket import socket
from typing import Any

from _socket import SO_BROADCAST, AF_INET, SOCK_DGRAM, SOL_SOCKET, IPPROTO_UDP, inet_aton
from sortedcontainers import SortedDict

from custom_components.artnet_led.client import OpCode, ArtBase, ArtPoll, ArtPollReply, PortAddress, IndicatorState, \
    PortAddressProgrammingAuthority, BootProcess, NodeReport, Port, PortType, StyleCode, FailsafeState, DiagnosticsMode, \
    DiagnosticsPriority, ArtIpProg, ArtIpProgReply, ArtDiagData, ArtTimeCode, ArtCommand, ArtTrigger

ARTNET_PORT = 0x1936
HA_OEM = 0x2BE9

HA_ESTA = 0x0  # TODO
RDM_SUPPORT = False  # TODO
SWITCH_TO_SACN_SUPPORT = False  # TODO
ART_ADDRESS_SUPPORT = False  # TODO


@dataclass
class Node:
    addr: bytes = [0x00] * 4,
    bind_index: int = 0,

    last_seen: time = time(),
    net_switch: int = 0,
    sub_switch: int = 0
    ports: list[Port] = None

    def get_addresses(self) -> set[PortAddress]:
        if not self.ports:
            return set()

        return set(map(
            lambda port: PortAddress(self.net_switch, self.sub_switch, port.sw_in),
            filter(
                lambda port: port.input,
                self.ports
            )
        ))

    def __hash__(self) -> int:
        return hash((self.addr, self.bind_index))


class ArtNetServer(asyncio.DatagramProtocol):
    def __init__(self, firmware_version: int = 0, oem: int = 0, esta=0, short_name: str = "PyArtNet",
                 long_name: str = "Python ArtNet Server", is_server_dhcp_configured: bool = True,
                 polling: bool = True):
        super().__init__()

        self.own_ip = inet_aton("192.168.1.35")

        self.firmware_version = firmware_version
        self.oem = oem
        self.esta = esta
        self.short_name = short_name
        self.long_name = long_name
        self.dhcp_configured = is_server_dhcp_configured
        self._polling = polling

        self.own_port_addresses = SortedDict()
        self.node_change_subscribers = set()

        self.nodes_by_ip = {}
        self.nodes_by_port_address = {}

        self.indicator_state = IndicatorState.LOCATE_IDENTIFY
        self.node_report = NodeReport.RC_POWER_OK
        self.status_message = "Starting ArtNet server..."
        self.art_poll_reply_counter = 0
        self.swout_text = "Output"
        self.swin_text = "Input"

        self.mac = uuid.getnode().to_bytes(6, "big")

    def add_port(self, port_address: PortAddress):
        port = Port(input=True, output=True, type=PortType.ART_NET,
                    sw_in=port_address.universe, sw_out=port_address.universe)

        self.own_port_addresses[port_address] = port
        self.update_subscribers()

    def remove_port(self, port_address: PortAddress):
        del self.own_port_addresses[port_address]
        self.update_subscribers()

    def get_port_bounds(self) -> (PortAddress, PortAddress):
        return self.own_port_addresses.peekitem(0)[0], self.own_port_addresses.peekitem(-1)[0]

    def get_node_by_ip(self, addr: bytes, bind_index: int = 1) -> Node | None:
        return self.nodes_by_ip.get((addr, bind_index), None)
        # return self.nodes_by_ip[addr, bind_index]

    def get_node_by_port_address(self, port_address: PortAddress) -> set[Node]:
        return self.nodes_by_port_address.get(port_address, set())

    def remove_node_by_ip(self, addr: bytes, bind_index: int = 1):
        del self.nodes_by_ip[addr, bind_index]

    def remove_node_by_port_address(self, port_address: PortAddress, node: Node):
        nodes = self.nodes_by_port_address[port_address]
        if not nodes:
            return
        nodes.remove(node)
        if not nodes:
            del self.nodes_by_port_address[port_address]

    def update_subscribers(self):
        print()
        # TODO

    def get_grouped_ports(self):
        # Sort the ports by their net and subnet
        net_sub = set(map(lambda p: (p.net, p.sub_net), self.own_port_addresses))
        grouped_list = [
            [
                ns[0],
                ns[1],
                [p.universe for p in self.own_port_addresses if (p.net, p.sub_net) == ns]
            ]
            for ns in net_sub
        ]

        for gli in grouped_list:
            # Chunk the universes into lists of at most 4
            chunked_universes = [gli[2][i:i + 4] for i in range(0, len(gli[2]), 4)]

            # Put the Port as value, instead of just universe number
            gli[2] = [
                list(map(lambda u: self.own_port_addresses[PortAddress(gli[0], gli[1], u)], chunked_universe))
                for chunked_universe in chunked_universes
            ]

        return grouped_list

    def start_server(self):
        loop = asyncio.new_event_loop()
        server_event = loop.create_datagram_endpoint(lambda: self, local_addr=('0.0.0.0', ARTNET_PORT))
        loop.set_debug(True)
        loop.run_until_complete(server_event)
        if self._polling:
            loop.create_task(server.start_poll_loop())
        print("Server started")
        return loop

    async def start_poll_loop(self):
        while True:
            poll = ArtPoll()
            poll.target_port_bounds = self.get_port_bounds()
            poll.notify_on_change = True
            poll.enable_diagnostics(DiagnosticsMode.UNICAST, DiagnosticsPriority.DP_HIGH)

            print("Sending ArtPoll")
            with socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP) as sock:
                sock.setsockopt(SOL_SOCKET, SO_BROADCAST, 1)
                # sock.setblocking(False)
                sock.sendto(poll.serialize(), ("255.255.255.255", 0x1936))

            print("Sleep 2.5 - 3 sec")
            await asyncio.sleep(3)

    def send_artnet(self, art_packet: ArtBase, ip: str):
        with socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP) as sock:
            sock.setblocking(False)
            sock.sendto(art_packet.serialize(), (ip, 0x1936))

    def connection_made(self, transport: transports.DatagramTransport) -> None:
        print("Connection made")
        super().connection_made(transport)

    def connection_lost(self, exc: Exception | None) -> None:
        super().connection_lost(exc)

    def datagram_received(self, data: bytes, addr: tuple[str | Any, int]) -> None:
        data = bytearray(data)
        opcode = ArtBase.peek_opcode(data)

        if opcode == OpCode.OP_POLL:
            poll = ArtPoll()
            poll.deserialize(data)

            print("Received ArtPoll")
            self.handle_poll(addr, poll)

        elif opcode == OpCode.OP_POLL_REPLY:
            reply = ArtPollReply()
            reply.deserialize(data)

            print(f"Received ArtPollReply from {reply.long_name}")
            self.handle_poll_reply(addr, reply)

        elif opcode == OpCode.OP_IP_PROG:
            print(f"Received IP prog request from {addr[0]}, ignoring...")

        elif opcode == OpCode.OP_IP_PROG_REPLY:
            ip_prog_reply = ArtIpProgReply()
            ip_prog_reply.deserialize(data)

            print(f"Received IP prog reply from {addr[0]}:\n"
                  f"  IP      : {ip_prog_reply.prog_ip}\n"
                  f"  Subnet  : {ip_prog_reply.prog_subnet}\n"
                  f"  Gateway : {ip_prog_reply.prog_gateway}\n"
                  f"  DHCP    : {ip_prog_reply.dhcp_enabled}")
            #                 TODO set port.good_input.data_received

        elif opcode == OpCode.OP_ADDRESS:
            print(f"Received Adress request from {addr[0]}, ignoring...")

        elif opcode == OpCode.OP_DIAG_DATA:
            diag_data = ArtDiagData()
            diag_data.deserialize(data)

            print(f"Received Diag Data from {addr[0]}:\n"
                  f"  Priority     : {diag_data.diag_priority}\n"
                  f"  Logical port : {diag_data.logical_port}\n"
                  f"  Text         : {diag_data.text}")

        elif opcode == OpCode.OP_TIME_CODE:
            timecode = ArtTimeCode()
            timecode.deserialize(data)

            print(f"Received Time Code from {addr[0]}:\n"
                  f"  Current time/frame : {timecode.hours}:{timecode.minutes}:{timecode.seconds}.{timecode.frames}\n"
                  f"  Type               : {timecode.type}")

        elif opcode == OpCode.OP_COMMAND:
            command = ArtCommand()
            command.deserialize(data)

            print(f"Received command from {addr[0]}\n"
                  f"  ESTA    : {command.esta}\n"
                  f"  Command : {command.command}")
            self.handle_command(command)

        elif opcode == OpCode.OP_TRIGGER:
            trigger = ArtTrigger()
            trigger.deserialize(data)

            print(f"Received trigger from {addr[0]}\n"
                  f"  OEM    : {trigger.oem}\n"
                  f"  Key    : {trigger.key}\n"
                  f"  Subkey : {trigger.sub_key}")
            self.handle_trigger(trigger)

    def should_handle_ports(self, lower_port: PortAddress, upper_port: PortAddress) -> bool:
        if not self.own_port_addresses:
            return False

        lowest_port_listener, upper_port_listener = self.get_port_bounds()

        return not (lower_port > upper_port_listener or upper_port < lowest_port_listener)

    def handle_poll_reply(self, addr, reply):
        if reply.node_report:
            print(f"  {reply.node_report}")
        ip_bytes = inet_aton(addr[0])
        # Maintain data structures
        bind_index = reply.bind_index
        node = self.get_node_by_ip(ip_bytes, bind_index)

        current_time = time()
        if not node:
            node = Node(ip_bytes, bind_index, current_time)
        else:
            node.last_seen = current_time
        old_addresses = node.get_addresses()
        node.net_switch = reply.net_switch
        node.sub_switch = reply.sub_switch
        node.ports = reply.ports
        new_addresses = node.get_addresses()
        addresses_to_remove = old_addresses - new_addresses

        for address_to_remove in addresses_to_remove:
            self.remove_node_by_port_address(address_to_remove, node)

        for new_address in new_addresses:
            self.get_node_by_port_address(new_address).add(node)
            if addr[0] != self.own_ip:
                self.status_message = "Discovered some ArtNet nodes!"

                if self.indicator_state == IndicatorState.LOCATE_IDENTIFY:
                    self.indicator_state = IndicatorState.MUTE_MODE

    def handle_poll(self, addr: tuple[str | Any, int], poll: ArtPoll):
        if poll.targeted_mode_enabled and not self.should_handle_ports(*poll.target_port_bounds):
            print("Received ArtPoll, but ignoring it since none of its universes overlap with out "
                  "universes.")
            return

        if poll.notify_on_change:
            self.node_change_subscribers.add(inet_aton(addr[0]))

        for (net, sub_net, ports_chunk) in self.get_grouped_ports():
            for ports in ports_chunk:
                node_report = self.node_report.report(self.art_poll_reply_counter, self.status_message)

                poll_reply = ArtPollReply(
                    source_ip=self.own_ip, firmware_version=self.firmware_version, net_switch=net,
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

                print("Responding to ArtPoll")

                with socket(AF_INET, SOCK_DGRAM) as sock:
                    sock.setblocking(False)
                    sock.sendto(packet, (addr[0], ARTNET_PORT))

                self.art_poll_reply_counter += 1

        if poll.is_diagnostics_enabled:
            diag_data = ArtDiagData(diag_priority=poll.diagnostics_priority, logical_port=0, text=self.status_message)
            packet = diag_data.serialize()

            with socket(AF_INET, SOCK_DGRAM) as sock:
                sock.setblocking(False)
                sock.sendto(packet, (addr[0], ARTNET_PORT))

    def handle_command(self, command):
        if command.esta == 0xFFFF:
            commands = command.command.split("&")
            for c in commands:
                c = c.strip(' ')
                if c:
                    key, value = c.split('=')
                    key = key.lower()
                    if key == 'SwoutText'.lower():
                        self.swout_text = value
                        print(f"Set Sw out text to: {value}")
                    elif key == 'SwinText'.lower():
                        self.swin_text = value
                        print(f"Set Sw in text to: {value}")
        # TODO check if it would be cool to add HA specific commands?

    def handle_trigger(self, trigger):
        # TODO possible integrations here
        #  0: ASCII inputs into HA?
        #  1: Define and activate Macro's
        #  2: Key press inputs into HA?
        #  3: Scenes!
        pass


server = ArtNetServer(firmware_version=1, short_name="Test python", long_name="Hello I am testing ArtNet server",
                      polling=True)
server.add_port(PortAddress(0, 0, 0))
server.add_port(PortAddress(0, 0, 1))

loop = server.start_server()

server.send_artnet(ArtCommand(command="SwoutText=Playback& SwinText=Record&"), "192.168.1.35")
server.send_artnet(ArtTrigger(key=1, sub_key=ord('F')), "192.168.1.35")

loop.run_forever()
