"""Local DNS forwarder that redirects only the car's MQTT name."""

import socket
import threading

from client import _handle


class DNSProxy:
    def __init__(self, local_ip: str):
        self.local_ip = local_ip
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.settimeout(0.5)
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._serve, name="dns-proxy", daemon=True)

    def start(self) -> None:
        self.socket.bind(("0.0.0.0", 53))
        self.thread.start()

    def _serve(self) -> None:
        while not self.stop_event.is_set():
            try:
                data, address = self.socket.recvfrom(4096)
            except socket.timeout:
                continue
            except OSError:
                break
            threading.Thread(
                target=_handle,
                args=(data, address, self.socket, self.local_ip),
                daemon=True,
            ).start()

    def stop(self) -> None:
        self.stop_event.set()
        self.socket.close()
        self.thread.join(timeout=2)
