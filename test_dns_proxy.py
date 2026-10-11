import socket
import struct
import unittest
from unittest.mock import patch

import client


def query(name: str) -> bytes:
    labels = b"".join(bytes([len(label)]) + label.encode() for label in name.split("."))
    return b"\x12\x34\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00" + labels + b"\x00\x00\x01\x00\x01"


class CaptureSocket:
    def __init__(self):
        self.sent = []

    def sendto(self, payload, address):
        self.sent.append((payload, address))


class DNSRoutingTests(unittest.TestCase):
    def test_mqtt_name_resolves_to_local_broker(self):
        sock = CaptureSocket()
        address = ("192.168.137.10", 53000)
        client._handle(query("oneoss-ecu-mqtt.geely.com"), address, sock, "192.168.137.1")
        answer, destination = sock.sent[0]
        self.assertEqual(destination, address)
        self.assertEqual(answer[-4:], socket.inet_aton("192.168.137.1"))
        self.assertEqual(struct.unpack_from(">H", answer, 6)[0], 1)

    def test_geely_https_api_is_forwarded_without_redirect(self):
        sock = CaptureSocket()
        upstream = b"\x12\x34\x81\x80"
        with patch.object(client, "_forward", return_value=upstream):
            client._handle(query("oneoss-ecu.geely.com"), ("192.168.137.10", 53000), sock, "192.168.137.1")
        self.assertEqual(sock.sent[0][0], upstream)


if __name__ == "__main__":
    unittest.main()
