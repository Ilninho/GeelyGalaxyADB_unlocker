"""Windows Mobile Hotspot lifecycle and its IPv4 interface."""

import asyncio
import json
import time

from windows_network import run_powershell


async def start_hotspot() -> bool:
    """Return true only when this process started the hotspot."""
    from winrt.windows.networking.connectivity import NetworkInformation
    from winrt.windows.networking.networkoperators import (
        NetworkOperatorTetheringManager,
        TetheringOperationalState,
        TetheringOperationStatus,
    )

    profile = NetworkInformation.get_internet_connection_profile()
    if profile is None:
        raise RuntimeError("Windows has no internet connection to share")
    manager = NetworkOperatorTetheringManager.create_from_connection_profile(profile)
    if manager.tethering_operational_state == TetheringOperationalState.ON:
        return False
    result = await manager.start_tethering_async()
    if result.status != TetheringOperationStatus.SUCCESS:
        raise RuntimeError(f"Windows could not start Mobile Hotspot: {result.status}")
    return True


async def stop_hotspot() -> None:
    from winrt.windows.networking.connectivity import NetworkInformation
    from winrt.windows.networking.networkoperators import NetworkOperatorTetheringManager

    profile = NetworkInformation.get_internet_connection_profile()
    if profile is not None:
        manager = NetworkOperatorTetheringManager.create_from_connection_profile(profile)
        await manager.stop_tethering_async()


def hotspot_interface(timeout: float = 20.0) -> tuple[int, str]:
    """Find the default Windows ICS address after the hotspot starts."""
    deadline = time.monotonic() + timeout
    script = (
        "$ErrorActionPreference='Stop'; "
        "$ip=Get-NetIPAddress -AddressFamily IPv4 | "
        "Where-Object { $_.IPAddress -eq '192.168.137.1' } | Select-Object -First 1; "
        "if ($ip) { @{index=$ip.InterfaceIndex;address=$ip.IPAddress} | ConvertTo-Json -Compress }"
    )
    while True:
        result = run_powershell(script)
        if result:
            data = json.loads(result)
            return int(data["index"]), str(data["address"])
        if time.monotonic() >= deadline:
            raise RuntimeError("Mobile Hotspot adapter 192.168.137.1 was not found")
        time.sleep(1)
