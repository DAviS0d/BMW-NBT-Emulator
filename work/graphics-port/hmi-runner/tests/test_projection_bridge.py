import base64
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from projection_bridge import ProjectionBridge, ProjectionUnavailable


class FakeStream:
    def __init__(self, payload):
        self.payload = bytearray(payload)
        self.sent = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def recv(self, count):
        result = bytes(self.payload[:count])
        del self.payload[:count]
        return result

    def sendall(self, data):
        self.sent.append(data)


class ProjectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.session = self.root / 'tools/playport/state/mib-session.properties'
        self.session.parent.mkdir(parents=True)
        self.secret = 'a' * 32
        self.session.write_text('url=http://127.0.0.1:8091\ntoken=' + self.secret + '\ntransport=usb\n')
        self.bridge = ProjectionBridge(self.root)

    def test_session_refuses_remote_and_credentials(self):
        for address in ['http://example.com:8091', 'http://127.0.0.1:8091/?x=y',
                        'http://user:password@127.0.0.1:8091', 'http://127.0.0.1:bad']:
            self.session.write_text('url=' + address + '\ntoken=' + self.secret)
            with self.assertRaises(ProjectionUnavailable):
                self.bridge._session()

    def test_status_returns_no_credentials_or_phone_identifier(self):
        status = {'sessionActive': True, 'phone': 'personal phone', 'display': {'width': 800, 'height': 480}}
        with patch.object(self.bridge, '_get', return_value=json.dumps(status).encode()):
            actual = self.bridge.status()
        self.assertTrue(actual['available'])
        self.assertFalse(actual['original_hmi_integration'])
        self.assertNotIn(self.secret, json.dumps(actual))
        self.assertNotIn('personal phone', json.dumps(actual))

    def test_invalid_frames_rejected(self):
        for data in [b'html error', b'\xff\xd8truncated']:
            with patch.object(self.bridge, '_get', return_value=data):
                with self.assertRaises(ProjectionUnavailable):
                    self.bridge.frame()

    def test_valid_frame_is_bytes(self):
        data = b'\xff\xd8jpeg\xff\xd9'
        with patch.object(self.bridge, '_get', return_value=data):
            self.assertEqual(data, self.bridge.frame())

    def test_controls_validate_and_reset(self):
        with patch.object(self.bridge, 'status', return_value={'available': True}):
            with patch.object(self.bridge, '_exchange') as exchange:
                result = self.bridge.action('carplay', 'select')
                self.assertTrue(result['sent'])
                self.assertEqual(exchange.call_args.args[0], [
                    {'type': 'knob', 'knob': {'select': True}}, {'type': 'knob', 'knob': {}}])
                with self.assertRaises(ValueError):
                    self.bridge.action('carplay', 'arbitrary')
                with self.assertRaises(ValueError):
                    self.bridge.touch('carplay', float('nan'), 0.5)

    def test_authenticated_websocket_masks_frames_and_waits_for_pong(self):
        random_bytes = b'x' * 16
        key = base64.b64encode(random_bytes).decode()
        accept = base64.b64encode(hashlib.sha1(
            (key + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest())
        header = b'HTTP/1.1 101 Switching Protocols\r\nSec-WebSocket-Accept: ' + accept + b'\r\n\r\n'
        pong = b'{"type":"pong"}'
        stream = FakeStream(header + bytes([0x81, len(pong)]) + pong)
        with patch('projection_bridge.socket.create_connection', return_value=stream):
            with patch('projection_bridge.os.urandom', side_effect=lambda n: b'x' * n):
                self.bridge._exchange([{'type': 'knob', 'knob': {'home': True}}])
        self.assertIn(self.secret.encode(), stream.sent[0])
        self.assertTrue(all(frame[1] & 128 for frame in stream.sent[1:]))
        self.assertEqual(stream.sent[-1][0], 0x88)

    def test_android_is_not_claimed_connected_without_video(self):
        result = self.bridge.status('android_auto')
        self.assertFalse(result['available'])
        self.assertFalse(result['original_hmi_integration'])


if __name__ == '__main__':
    unittest.main()
