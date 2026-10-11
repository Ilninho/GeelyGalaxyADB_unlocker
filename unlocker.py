"""Run the local Geely MQTT broker and, on Windows, the hotspot DNS bridge."""

import argparse
import asyncio
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import threading
import time
import uuid

import broker


def packaged_file(name: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / "tls" / name


def certificate_paths(args: argparse.Namespace) -> tuple[Path, Path]:
    cert = Path(args.cert) if args.cert else packaged_file("fullchain.pem")
    key = Path(args.key) if args.key else packaged_file("privkey.pem")
    if not cert.is_file() or not key.is_file():
        raise RuntimeError(
            "A trusted TLS certificate is required. This build has none; "
            "supply --cert and --key or use a release built with a dedicated project certificate."
        )
    return cert, key


def _state_file() -> Path:
    root = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "GeelyGalaxyADBUnlocker"
    root.mkdir(parents=True, exist_ok=True)
    return root / "network-state.json"


def _save_state(path: Path, state, rules: list[str], started_hotspot: bool) -> None:
    payload = {"dns": state.to_dict(), "firewall_rules": rules, "started_hotspot": started_hotspot}
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload), encoding="utf-8")
    os.replace(tmp, path)


def _firewall_rule(name: str, port: int, protocol: str, local_ip: str) -> None:
    subprocess.run(
        ["netsh", "advfirewall", "firewall", "add", "rule", f"name={name}",
         "dir=in", "action=allow", f"protocol={protocol}", f"localport={port}",
         f"localip={local_ip}", "remoteip=localsubnet"],
        check=True, capture_output=True,
    )


def _delete_firewall_rule(name: str) -> None:
    from windows_network import run_powershell
    run_powershell(
        "$ErrorActionPreference='Stop'; "
        f"Get-NetFirewallRule -DisplayName '{name}' -ErrorAction SilentlyContinue | Remove-NetFirewallRule"
    )


def _restore_saved(path: Path, *, stop_hotspot_if_started: bool = True) -> None:
    if not path.exists():
        return
    from windows_network import NetworkState, restore_dns
    data = json.loads(path.read_text(encoding="utf-8"))
    state = NetworkState.from_dict(data["dns"])
    restore_dns(state)
    for name in data.get("firewall_rules", []):
        if re.fullmatch(r"GeelyGalaxyUnlocker-[0-9a-f]{12}-(?:DNS|MQTT)", name):
            _delete_firewall_rule(name)
    if stop_hotspot_if_started and data.get("started_hotspot"):
        from hotspot_windows import stop_hotspot
        asyncio.run(stop_hotspot())
    path.unlink()


def _start_broker(cert: Path, key: Path) -> threading.Thread:
    errors = []

    def serve():
        try:
            asyncio.run(broker.main("0.0.0.0", 8883, str(cert), str(key)))
        except Exception as exc:
            errors.append(exc)

    thread = threading.Thread(target=serve, name="mqtt-broker", daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if errors:
            raise RuntimeError(f"MQTT broker failed: {errors[0]}")
        try:
            with socket.create_connection(("127.0.0.1", 8883), timeout=0.2):
                return thread
        except OSError:
            time.sleep(0.1)
    raise RuntimeError("MQTT broker did not start on TCP 8883")


def run_windows(cert: Path, key: Path) -> None:
    import msvcrt
    from client import require_admin
    from dns_proxy import DNSProxy
    from hotspot_windows import hotspot_interface, start_hotspot, stop_hotspot
    from windows_network import capture_dns, set_dns

    require_admin()
    path = _state_file()
    lock = path.with_suffix(".lock").open("a+b")
    lock.seek(0)
    try:
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError as exc:
        raise RuntimeError("Another unlocker instance is running") from exc

    started_hotspot = False
    proxy = None
    try:
        _restore_saved(path)
        try:
            index, local_ip = hotspot_interface(timeout=0)
        except RuntimeError:
            started_hotspot = asyncio.run(start_hotspot())
            index, local_ip = hotspot_interface()

        broker_thread = _start_broker(cert, key)
        proxy = DNSProxy(local_ip)
        proxy.start()

        state = capture_dns(index)
        run_id = uuid.uuid4().hex[:12]
        rules = [f"GeelyGalaxyUnlocker-{run_id}-DNS", f"GeelyGalaxyUnlocker-{run_id}-MQTT"]
        _save_state(path, state, rules, started_hotspot)
        _firewall_rule(rules[0], 53, "UDP", local_ip)
        _firewall_rule(rules[1], 8883, "TCP", local_ip)
        set_dns(state, "127.0.0.1")

        print(f"Local MQTT broker: {local_ip}:8883")
        print("Connect the car to this laptop's Mobile Hotspot. USB is optional.")
        print("Press Ctrl+C to stop and restore DNS and firewall settings.")
        while True:
            time.sleep(1)
            if not broker_thread.is_alive():
                raise RuntimeError("MQTT broker stopped unexpectedly")
    finally:
        try:
            if path.exists():
                _restore_saved(path, stop_hotspot_if_started=False)
        finally:
            try:
                if proxy is not None:
                    proxy.stop()
            finally:
                try:
                    if started_hotspot:
                        asyncio.run(stop_hotspot())
                finally:
                    lock.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Local Geely ADB MQTT unlocker")
    parser.add_argument("--cert", help="trusted TLS full chain PEM; defaults to packaged certificate")
    parser.add_argument("--key", help="matching private key PEM; defaults to packaged key")
    parser.add_argument("--broker-only", action="store_true", help="run broker only; configure Wi-Fi and DNS separately")
    args = parser.parse_args()
    try:
        cert, key = certificate_paths(args)
        if args.broker_only:
            asyncio.run(broker.main("0.0.0.0", 8883, str(cert), str(key)))
        elif sys.platform == "win32":
            run_windows(cert, key)
        else:
            raise RuntimeError("Automatic hotspot and DNS are currently supported only on Windows; use --broker-only")
    except KeyboardInterrupt:
        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
