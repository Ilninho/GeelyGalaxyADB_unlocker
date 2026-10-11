import json
import unittest
from unittest.mock import patch

import windows_network


class NetworkStateTests(unittest.TestCase):
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

    def test_snapshot_round_trip_preserves_mode_and_adapter_identity(self):
        state = windows_network.NetworkState(17, "{01234567-89ab-cdef-0123-456789abcdef}", ("9.9.9.9",))
        self.assertEqual(windows_network.NetworkState.from_dict(json.loads(json.dumps(state.to_dict()))), state)


if __name__ == "__main__":
    unittest.main()
