"""Capture and restore the IPv4 DNS setting changed by the Windows client."""

from dataclasses import dataclass
import ipaddress
import json
import re
import subprocess


def run_powershell(script: str) -> str:
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
        check=True,
        capture_output=True,
        text=True,
        errors="replace",
    )
    return result.stdout.strip()


@dataclass(frozen=True)
class NetworkState:
    interface_index: int
    interface_guid: str
    static_ipv4_dns: tuple[str, ...]

    def to_dict(self) -> dict:
        return {
            "interface_index": self.interface_index,
            "interface_guid": self.interface_guid,
            "static_ipv4_dns": list(self.static_ipv4_dns),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "NetworkState":
        index = int(data["interface_index"])
        if index < 1:
            raise ValueError("invalid interface index")
        guid = str(data["interface_guid"])
        if not re.fullmatch(r"\{[0-9a-fA-F-]{36}\}", guid):
            raise ValueError("invalid interface GUID")
        addresses = tuple(str(ipaddress.IPv4Address(value)) for value in data["static_ipv4_dns"])
        return cls(index, guid, addresses)


def capture_dns(interface_index: int) -> NetworkState:
    index = int(interface_index)
    if index < 1:
        raise ValueError("invalid interface index")
    output = run_powershell(
        "$ErrorActionPreference='Stop'; "
        f"$a=Get-NetAdapter -InterfaceIndex {index}; "
        "if (-not $a) { throw 'adapter not found' }; "
        "$guid='{' + $a.InterfaceGuid.ToString() + '}'; "
        "$path='HKLM:\\SYSTEM\\CurrentControlSet\\Services\\Tcpip\\Parameters\\Interfaces\\' + $guid; "
        "$nameserver=(Get-ItemProperty -LiteralPath $path -Name NameServer -ErrorAction SilentlyContinue).NameServer; "
        "@{interface_index=$a.ifIndex;interface_guid=$guid;nameserver=[string]$nameserver} | ConvertTo-Json -Compress"
    )
    data = json.loads(output)
    raw = data["nameserver"].strip()
    addresses = re.split(r"[\s,]+", raw) if raw else []
    return NetworkState.from_dict({
        "interface_index": data["interface_index"],
        "interface_guid": data["interface_guid"],
        "static_ipv4_dns": addresses,
    })


def _identity_check(state: NetworkState) -> str:
    return (
        f"$a=Get-NetAdapter -InterfaceIndex {state.interface_index}; "
        f"if (-not $a -or ('{{' + $a.InterfaceGuid.ToString() + '}}') -ne '{state.interface_guid}') "
        "{ throw 'adapter identity changed; refusing DNS edit' }; "
    )


def set_dns(state: NetworkState, address: str) -> None:
    ip = str(ipaddress.IPv4Address(address))
    run_powershell(
        "$ErrorActionPreference='Stop'; " + _identity_check(state)
        + f"Set-DnsClientServerAddress -InterfaceIndex {state.interface_index} -ServerAddresses @('{ip}')"
    )


def restore_dns(state: NetworkState) -> None:
    command = (
        "-ServerAddresses @(" + ",".join(f"'{address}'" for address in state.static_ipv4_dns) + ")"
        if state.static_ipv4_dns else "-ResetServerAddresses"
    )
    run_powershell(
        "$ErrorActionPreference='Stop'; " + _identity_check(state)
        + f"Set-DnsClientServerAddress -InterfaceIndex {state.interface_index} {command}"
    )
