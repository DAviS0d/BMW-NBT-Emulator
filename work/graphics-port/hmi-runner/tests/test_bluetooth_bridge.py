import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bluetooth_bridge import BluetoothBridge


class BluetoothTests(unittest.TestCase):
    def test_missing_radio_prevents_transport_start(self):
        with patch('bluetooth_bridge.radio_present', return_value=False):
            bridge = BluetoothBridge()
            self.assertFalse(bridge.status()['radio_present'])
            self.assertFalse(bridge.status()['original_hmi_integration'])
            with patch('bluetooth_bridge.subprocess.Popen') as spawn:
                with self.assertRaises(RuntimeError):
                    bridge.start()
                spawn.assert_not_called()
            bridge.close()

    def test_commands_validate_before_any_device_action(self):
        for bad in ({'cmd': 'scan', 'seconds': 999}, {'cmd': 'scan', 'seconds': True},
                    {'cmd': 'pair', 'addr': 'bad'}, {'cmd': 'passkey_reply', 'accept': 'yes'},
                    {'cmd': 'control', 'what': 'unknown'}, {'cmd': 'unpair'},
                    {'cmd': 'paired', 'demo': True}):
            with self.subTest(command=bad):
                with self.assertRaises(ValueError):
                    BluetoothBridge.validate(bad)
        for good in ({'cmd': 'paired'}, {'cmd': 'scan', 'seconds': 5},
                     {'cmd': 'pair', 'addr': '01:23:45:67:89:AB'},
                     {'cmd': 'passkey_reply', 'accept': False},
                     {'cmd': 'control', 'what': 'pause'}):
            self.assertEqual(BluetoothBridge.validate(good), good)


if __name__ == '__main__':
    unittest.main()
