import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

import unlocker
import windows_network
import hotspot_windows


class RecoveryTests(unittest.TestCase):
    def test_stale_snapshot_restores_dns_and_owned_firewall_rule(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "network-state.json"
            path.write_text(json.dumps({
                "dns": {
                    "interface_index": 17,
                    "interface_guid": "{01234567-89ab-cdef-0123-456789abcdef}",
                    "static_ipv4_dns": ["9.9.9.9", "1.1.1.1"],
                },
                "firewall_rules": ["GeelyGalaxyUnlocker-0123456789ab-DNS"],
                "started_hotspot": False,
            }), encoding="utf-8")
            commands = []
            with patch.object(windows_network, "run_powershell", side_effect=commands.append):
                unlocker._restore_saved(path)
            self.assertFalse(path.exists())
            self.assertEqual(len(commands), 2)
            self.assertIn("-ServerAddresses @('9.9.9.9','1.1.1.1')", commands[0])
            self.assertIn("GeelyGalaxyUnlocker-0123456789ab-DNS", commands[1])

    def test_failed_dns_restore_keeps_snapshot_for_next_attempt(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "network-state.json"
            path.write_text(json.dumps({
                "dns": {
                    "interface_index": 17,
                    "interface_guid": "{01234567-89ab-cdef-0123-456789abcdef}",
                    "static_ipv4_dns": [],
                },
                "firewall_rules": [],
            }), encoding="utf-8")
            with patch.object(windows_network, "run_powershell", side_effect=RuntimeError("adapter missing")):
                with self.assertRaises(RuntimeError):
                    unlocker._restore_saved(path)
            self.assertTrue(path.exists())

    def test_crash_recovery_stops_hotspot_if_previous_run_started_it(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "network-state.json"
            path.write_text(json.dumps({
                "dns": {
                    "interface_index": 17,
                    "interface_guid": "{01234567-89ab-cdef-0123-456789abcdef}",
                    "static_ipv4_dns": [],
                },
                "firewall_rules": [],
                "started_hotspot": True,
            }), encoding="utf-8")
            with patch.object(windows_network, "run_powershell", return_value=""):
                with patch.object(hotspot_windows, "stop_hotspot", new_callable=AsyncMock) as stop:
                    unlocker._restore_saved(path)
            stop.assert_awaited_once()
            self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
