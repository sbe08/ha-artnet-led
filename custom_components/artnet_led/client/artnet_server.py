from enum import Enum
from socket import socket

from _socket import SO_BROADCAST, AF_INET, SOCK_DGRAM, SOL_SOCKET, SO_REUSEADDR, IPPROTO_UDP, inet_aton, IPPROTO_IP, \
    IP_ADD_MEMBERSHIP, INADDR_ANY, getaddrinfo, inet_pton

from custom_components.artnet_led.client import OpCode, ArtBase, ArtPoll, ArtPollReply

ARTNET_PORT = 0x1936





def start_server():
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
                print(f"{opcode}: {data}")

            elif opcode == OpCode.OP_POLL_REPLY:
                reply = ArtPollReply()
                reply.deserialize(data)
                print(f"{opcode}: {data}")

start_server()