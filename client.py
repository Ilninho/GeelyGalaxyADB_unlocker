import sys
import ctypes
from ctypes import wintypes
import subprocess
import socket
import struct
import threading
import atexit
import argparse
import encodings.idna

VPS_HOST = "YOU_DOMAIN"

REDIRECT_HOSTS = {
    "oneoss-ecu-mqtt.geely.com",
    "oneoss-ecu-mqtt.geely.com.",
}

UPSTREAM_DNS = ("1.1.1.1", 53)

def _print(msg):     print(f"  {msg}", flush=True)
def ok(msg):         print(f"  [+] {msg}", flush=True)
def warn(msg):       print(f"  [!] {msg}", flush=True)
def fail(msg):       print(f"  [x] {msg}", flush=True); input("\n  Press Enter to exit..."); sys.exit(1)

def _is_frozen():
    return getattr(sys, "frozen", False) or "__compiled__" in globals()

def require_admin():
    try:
        if ctypes.windll.shell32.IsUserAnAdmin():
            return
    except Exception:
        pass
    if _is_frozen():
        target, params = sys.executable, " ".join(f'"{a}"' for a in sys.argv[1:])
    else:
        target, params = sys.executable, " ".join(f'"{a}"' for a in sys.argv)
    rc = ctypes.windll.shell32.ShellExecuteW(None, "runas", target, params, None, 1)
    if rc <= 32:
        print(f"  [x] Elevation failed (code {rc}).", flush=True)
        input("\n  Press Enter to exit...")
    sys.exit(0 if rc > 32 else 1)

def resolve_vps(value: str) -> str:
    try:
        socket.inet_aton(value)
        return value
    except OSError:
        pass
    ascii_host = value.encode("idna").decode("ascii")
    return socket.gethostbyname(ascii_host)

def find_hotspot_adapter() -> str | None:
    ps = r"""
$ErrorActionPreference = 'SilentlyContinue'
$a = Get-NetIPAddress -AddressFamily IPv4 |
     Where-Object { $_.IPAddress -eq '192.168.137.1' } |
     Select-Object -First 1 -ExpandProperty ifIndex
if (-not $a) {
  $a = Get-NetAdapter |
       Where-Object { $_.Status -eq 'Up' -and $_.InterfaceDescription -match 'Wi-?Fi Direct' } |
       Where-Object { Get-NetIPAddress -InterfaceIndex $_.ifIndex -AddressFamily IPv4 |
                      Where-Object { $_.IPAddress -like '192.168.137.*' } } |
       Select-Object -First 1 -ExpandProperty Name
}
if (-not $a) {
  $a = Get-NetAdapter |
       Where-Object { $_.Status -eq 'Up' -and $_.InterfaceDescription -match 'Wi-?Fi Direct' } |
       Select-Object -First 1 -ExpandProperty Name
}
$a
"""
    result = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
        capture_output=True, text=True, errors="replace"
    )
    if result.stdout:
        for line in result.stdout.splitlines():
            line = line.strip()
            if line:
                return line
    return None


def set_adapter_dns(adapter: str, dns: str):
    subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         f"Set-DnsClientServerAddress -InterfaceIndex '{adapter}' -ServerAddresses '{dns}'"],
        check=True, capture_output=True
    )


def reset_adapter_dns(adapter: str):
    subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         f"Set-DnsClientServerAddress -InterfaceIndex '{adapter}' -ResetServerAddresses"],
        capture_output=True
    )


def open_firewall():
    existing = subprocess.run(
        ["netsh", "advfirewall", "firewall", "show", "rule", "name=Geely-DNS-53"],
        capture_output=True
    )
    if existing.stdout and b"Geely-DNS-53" in existing.stdout:
        return
    subprocess.run(
        ["netsh", "advfirewall", "firewall", "add", "rule",
         "name=Geely-DNS-53", "dir=in", "action=allow",
         "protocol=UDP", "localport=53"],
        capture_output=True
    )


def close_firewall():
    subprocess.run(
        ["netsh", "advfirewall", "firewall", "delete", "rule",
         "name=Geely-DNS-53"],
        capture_output=True
    )

_HANDLER_ROUTINE = getattr(ctypes, "WINFUNCTYPE", ctypes.CFUNCTYPE)(wintypes.BOOL, wintypes.DWORD)
_ctrl_handler_ref = None
_cleanup_lock = threading.Lock()
_cleanup_done = False
_cleanup_adapter: str | None = None


def _cleanup():
    global _cleanup_done
    with _cleanup_lock:
        if _cleanup_done:
            return
        _cleanup_done = True
    _print("Restoring network settings...")
    if _cleanup_adapter:
        reset_adapter_dns(_cleanup_adapter)
    close_firewall()
    ok("Done.")
    print()


def _console_ctrl_handler(ctrl_type):
    _cleanup()
    return False


def install_cleanup(adapter: str):
    global _cleanup_adapter, _ctrl_handler_ref
    _cleanup_adapter = adapter
    atexit.register(_cleanup)
    _ctrl_handler_ref = _HANDLER_ROUTINE(_console_ctrl_handler)
    ctypes.windll.kernel32.SetConsoleCtrlHandler(_ctrl_handler_ref, True)

def _parse_name(data: bytes, offset: int) -> tuple[str, int]:
    labels = []
    while True:
        length = data[offset]
        if length == 0:
            offset += 1
            break
        if (length & 0xC0) == 0xC0:
            ptr = ((length & 0x3F) << 8) | data[offset + 1]
            name_part, _ = _parse_name(data, ptr)
            labels.append(name_part)
            offset += 2
            break
        offset += 1
        labels.append(data[offset:offset + length].decode("ascii", errors="replace"))
        offset += length
    return ".".join(labels), offset


QTYPE_A = 1
QTYPE_NAMES = {1: "A", 28: "AAAA", 5: "CNAME", 15: "MX", 2: "NS", 12: "PTR"}


def _build_response(query: bytes, ip: str) -> bytes:
    tx_id = query[:2]
    _, end = _parse_name(query, 12)
    qtype = struct.unpack_from(">H", query, end)[0]
    question = query[12:end + 4]
    if qtype == QTYPE_A:
        header = tx_id + struct.pack(">H", 0x8580) + b"\x00\x01\x00\x01\x00\x00\x00\x00"
        answer = b"\xc0\x0c\x00\x01\x00\x01\x00\x00\x00\x3c\x00\x04" + socket.inet_aton(ip)
    else:
        header = tx_id + struct.pack(">H", 0x8580) + b"\x00\x01\x00\x00\x00\x00\x00\x00"
        answer = b""
    return header + question + answer


def _query_name_type(data: bytes) -> tuple[str, int] | None:
    try:
        name, end = _parse_name(data, 12)
        qtype = struct.unpack_from(">H", data, end)[0]
        return name.rstrip("."), qtype
    except Exception:
        return None


def _forward(data: bytes) -> bytes | None:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(3)
        s.sendto(data, UPSTREAM_DNS)
        r, _ = s.recvfrom(4096)
        return r
    except Exception:
        return None
    finally:
        s.close()


def _handle(data: bytes, addr: tuple, sock: socket.socket, vps_ip: str):
    parsed = _query_name_type(data)
    name, qtype = parsed if parsed else (None, None)
    qtype_label = QTYPE_NAMES.get(qtype, qtype)
    if name and name.lower() in REDIRECT_HOSTS:
        print(f"  [->] REDIRECT {name} ({qtype_label}) from {addr[0]}", flush=True)
        sock.sendto(_build_response(data, vps_ip), addr)
    else:
        print(f"  [ ] passthrough {name} ({qtype_label}) from {addr[0]}", flush=True)
        r = _forward(data)
        if r:
            sock.sendto(r, addr)


def run_dns_proxy(vps_ip: str):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind(("0.0.0.0", 53))
    except PermissionError:
        fail("Cannot bind to port 53. Run as Administrator.")
    except OSError as e:
        fail(f"Port 53 unavailable: {e}\nStop the DNS Client service and try again.")

    while True:
        try:
            data, addr = sock.recvfrom(512)
            threading.Thread(
                target=_handle, args=(data, addr, sock, vps_ip), daemon=True
            ).start()
        except KeyboardInterrupt:
            break
        except Exception:
            pass

def main():
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--vps", default=VPS_HOST)
    args = ap.parse_args()

    require_admin()

    print()
    print("  ╔══════════════════════════════════════╗")
    print("  ║        Geely ADB Enabler             ║")
    print("  ╚══════════════════════════════════════╝")
    print()

    _print("Connecting to broker...")
    try:
        vps_ip = resolve_vps(args.vps)
        ok("Broker ready.")
    except Exception as e:
        fail(f"Cannot reach broker: {e}")

    _print("Looking for Mobile Hotspot adapter...")
    adapter = find_hotspot_adapter()
    if not adapter:
        warn("Mobile Hotspot adapter not found.")
        warn("Enable Mobile Hotspot in Windows Settings, then run again.")
        input("\n  Press Enter to exit...")
        sys.exit(1)
    ok(f"Hotspot adapter found: {adapter}")

    _print("Configuring network...")
    try:
        set_adapter_dns(adapter, "127.0.0.1")
    except Exception as e:
        fail(f"Failed to configure network: {e}")

    open_firewall()
    ok("Network configured.")

    install_cleanup(adapter)

    print()
    print("  ──────────────────────────────────────────")
    print("  Ready. Connect your car to the hotspot.")
    print("  ADB will be enabled automatically (~30 sec).")
    print()
    print("  Press Ctrl+C to stop and restore settings.")
    print("  ──────────────────────────────────────────")
    print()

    try:
        run_dns_proxy(vps_ip)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except BaseException as e:
        import traceback
        print("\n  [x] Unhandled error:\n", flush=True)
        traceback.print_exc()
        input("\n  Press Enter to exit...")
        sys.exit(1)
