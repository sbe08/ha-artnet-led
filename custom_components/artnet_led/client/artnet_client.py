import socket
import struct

from custom_components.artnet_led.client import ArtPoll, DiagnosticsMode, DiagnosticsPriority, PortAddress, \
    ArtPollReply, CLIENT_VERSION, IndicatorState, PortAddressProgrammingAuthority, BootProcess, Port, StyleCode, \
    FailsafeState


def send_update():
    host = "192.168.1.35"
    port = 6454
    universe_nr = 0
    sequence_counter = 0  # jnimmo's is always 0, pyartnet is [0, 254], which is compliant with the spec
    highest_channel = 10
    data = bytearray()
    data.extend([255, 255, 255, 255, 255, 255, 255, 255, 255, 255])

    packet = bytearray()

    packet.extend(map(ord, "Art-Net"))
    packet.append(0x00)  # Null terminate Art-Net
    packet.extend([0x00, 0x50])  # Opcode ArtDMX 0x5000 (Little endian)
    packet.extend([0x00, 0x0e])  # Protocol version 14
    packet.append(sequence_counter)  # Sequence,
    packet.append(0x00)  # Physical
    packet.append(universe_nr & 0xFF)  # Universe LowByte
    packet.append(universe_nr >> 8 & 0xFF)  # Universe HighByte
    # packet.extend([universe_nr, 0x00])  # Universe
    packet.extend(struct.pack('>h', highest_channel))
    packet.extend(data)

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)  # UDP
    s.setblocking(False)
    s.sendto(packet, (host, port))


def poll_broadcast():
    package = ArtPoll().serialize()

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.setblocking(False)
        sock.sendto(package, ("255.255.255.255", 0x1936))


def reply():
    local_ip_str = socket.gethostbyname(socket.gethostname())
    local_ip = socket.inet_aton(local_ip_str)

    package = ArtPollReply(
        local_ip,
        CLIENT_VERSION,
        PortAddress(0, 0, 1),
        0x2BE9,
        IndicatorState.NORMAL_MODE,
        PortAddressProgrammingAuthority.PROGRAMMATIC,
        BootProcess.FLASH,
        False,
        0,
        "HomeAssistant",
        "HomeAssistant Art-Net integration",
        "",
        [Port()],
        0,
        0,
        0,
        StyleCode.ST_CONTROLLER,
        bytearray([0, 1, 2, 3, 4, 5]),
        bytearray([192, 168, 1, 35]),
        0,
        True,
        True,
        True,
        True,
        False,
        False,
        False,
        False,
        FailsafeState.HOLD_LAST_STATE,
        False,
        False
    )

    return package

poll_broadcast()

# set port.goodoutputa.data_being_transmitted when doing ArtNetSync