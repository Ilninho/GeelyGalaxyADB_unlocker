import json
import unittest
from unittest.mock import patch

import windows_network


class NetworkStateTests(unittest.TestCase):
    def test_capture_preserves_static_dns_addresses(self):
        result = '{"interface_index":17,"interface_guid":"{01234567-89ab-cdef-0123-456789abcdef}","nameserver":"9.9.9.9,1.1.1.1"}'
        with patch.object(windows_network, "run_powershell", return_value=result):
            state = windows_network.capture_dns(17)
        self.assertEqual(state.static_ipv4_dns, ("9.9.9.9", "1.1.1.1"))

    def test_capture_preserves_dhcp_dns_mode(self):
        result = '{"interface_index":17,"interface_guid":"{01234567-89ab-cdef-0123-456789abcdef}","nameserver":""}'
        with patch.object(windows_network, "run_powershell", return_value=result):
            state = windows_network.capture_dns(17)
        self.assertEqual(state.static_ipv4_dns, ())

    def test_restore_keeps_preexisting_static_dns_in_order(self):
        state = windows_network.NetworkState(17, "{01234567-89ab-cdef-0123-456789abcdef}", ("9.9.9.9", "1.1.1.1"))
        commands = []

        with patch.object(windows_network, "run_powershell", side_effect=commands.append):
            windows_network.restore_dns(state)

        self.assertEqual(len(commands), 1)
        self.assertIn("-InterfaceIndex 17", commands[0])
        self.assertIn("-ServerAddresses @('9.9.9.9','1.1.1.1')", commands[0])
        self.assertNotIn("-ResetServerAddresses", commands[0])

    def test_restore_returns_dhcp_dns_mode(self):
        state = windows_network.NetworkState(17, "{01234567-89ab-cdef-0123-456789abcdef}", ())
        commands = []

        with patch.object(windows_network, "run_powershell", side_effect=commands.append):
            windows_network.restore_dns(state)

        self.assertEqual(len(commands), 1)
        self.assertIn("-ResetServerAddresses", commands[0])

    def test_guid_accepted_with_or_without_braces(self):
        for raw in ("{01234567-89AB-cdef-0123-456789abcdef}", "01234567-89ab-cdef-0123-456789abcdef"):
            state = windows_network.NetworkState.from_dict(
                {"interface_index": 17, "interface_guid": raw, "static_ipv4_dns": []})
            self.assertEqual(state.interface_guid, "{01234567-89ab-cdef-0123-456789abcdef}")

    def test_double_braced_guid_is_rejected(self):
        with self.assertRaises(ValueError):
            windows_network.NetworkState.from_dict(
                {"interface_index": 17, "interface_guid": "{{01234567-89ab-cdef-0123-456789abcdef}}", "static_ipv4_dns": []})

    def test_snapshot_round_trip_preserves_mode_and_adapter_identity(self):
        state = windows_network.NetworkState(17, "{01234567-89ab-cdef-0123-456789abcdef}", ("9.9.9.9",))
        self.assertEqual(windows_network.NetworkState.from_dict(json.loads(json.dumps(state.to_dict()))), state)


if __name__ == "__main__":
    unittest.main()
