"""Reuse local PlayPort and Android DHU transports without exposing credentials.

CarPlay JPEGs are supplied by the existing PlayPort browser decoder. This module
does not claim to add a native BMW menu item or implement the projection protocol.
"""
from __future__ import annotations

import base64
import hashlib
import json
import math
import os
from pathlib import Path
import re
import socket
import struct
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request


class ProjectionUnavailable(RuntimeError):
    """A public, sanitized error which never includes a credential-bearing URL."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class ProjectionBridge:
    def __init__(self, mib_root=None, timeout=2.0):
        self.root = Path(mib_root or r'G:\mibstd2-emulator\mib2emu')
        self.timeout = timeout
        self._lock = threading.RLock()
        self._status_cache = {}
        # Explicitly ignore system proxies for the credentialed loopback endpoint.
        self._http = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())

    def _session(self):
        path = self.root / 'tools/playport/state/mib-session.properties'
        try:
            text = path.read_text(encoding='utf-8-sig')
        except OSError:
            raise ProjectionUnavailable('No local PlayPort session is configured') from None
        props = {}
        for line in text.splitlines():
            if '=' in line and not line.lstrip().startswith(('#', '!')):
                key, value = line.split('=', 1)
                props[key.strip()] = value.strip().replace(r'\:', ':').replace(r'\=', '=')
        url, token = props.get('url', ''), props.get('token', '')
        try:
            parsed = urllib.parse.urlsplit(url)
            port = parsed.port
        except ValueError:
            raise ProjectionUnavailable('Invalid local PlayPort session address') from None
        if (parsed.scheme != 'http' or parsed.hostname != '127.0.0.1'
                or not port or parsed.username or parsed.password
                or parsed.path not in ('', '/') or parsed.query or parsed.fragment
                or not re.fullmatch(r'[0-9a-fA-F]{32}', token)):
            raise ProjectionUnavailable('PlayPort session must use token-authenticated HTTP on 127.0.0.1')
        return f'http://127.0.0.1:{port}', token, props.get('transport', 'unknown')

    def _get(self, url, limit):
        try:
            with self._http.open(url, timeout=self.timeout) as response:
                data = response.read(limit + 1)
                if len(data) > limit:
                    raise ProjectionUnavailable('Projection response exceeded the size limit')
                return data
        except (OSError, urllib.error.URLError, ValueError):
            # urllib errors include the token-bearing request URL. Never forward them.
            raise ProjectionUnavailable('Local projection receiver is unavailable or has no live frame') from None

    def status(self, kind='carplay', refresh=False):
        if kind not in ('carplay', 'android_auto'):
            raise ValueError('Unknown projection source')
        with self._lock:
            cached = self._status_cache.get(kind)
            if not refresh and cached and time.monotonic() - cached[0] < 1:
                return dict(cached[1])
        result = self._carplay_status() if kind == 'carplay' else self._android_status()
        with self._lock:
            self._status_cache[kind] = time.monotonic(), result
        return dict(result)

    def _carplay_status(self):
        try:
            endpoint, _, transport = self._session()
            data = json.loads(self._get(endpoint + '/api/status', 65536))
            if not isinstance(data, dict):
                raise ValueError()
            display = data.get('display') or {}
            if not isinstance(display, dict):
                raise ValueError()
            return {'source': 'carplay', 'available': bool(data.get('sessionActive')),
                    'receiver_running': True, 'transport': transport,
                    'width': display.get('width'), 'height': display.get('height'),
                    'fps': display.get('fps'), 'frame_source': 'PlayPort decoded JPEG',
                    'native_bmw_menu': False, 'original_hmi_integration': False,
                    'message': 'Phone projection session active' if data.get('sessionActive')
                    else 'Receiver is running; waiting for an iPhone session'}
        except (ProjectionUnavailable, ValueError, TypeError):
            return {'source': 'carplay', 'available': False, 'receiver_running': False,
                    'native_bmw_menu': False, 'original_hmi_integration': False,
                    'message': 'Local PlayPort receiver is unavailable'}

    def _android_status(self):
        adb = self.root / 'tools/platform-tools/adb.exe'
        dhu = self.root / 'tools/dhu/desktop-head-unit.exe'
        result = {'source': 'android_auto', 'available': False,
                  'adb_installed': adb.is_file(), 'dhu_installed': dhu.is_file(),
                  'authorized_devices': 0, 'unauthorized_devices': 0,
                  'native_bmw_menu': False, 'original_hmi_integration': False}
        if not adb.is_file():
            result['message'] = 'Android platform tools are not installed'
            return result
        try:
            process = subprocess.run([str(adb), 'devices'], capture_output=True, text=True,
                                     timeout=self.timeout,
                                     creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            if process.returncode:
                raise OSError()
            # Do not return phone serial numbers or adb diagnostics.
            for line in process.stdout.splitlines():
                fields = line.split()
                if len(fields) == 2 and fields[1] == 'device':
                    result['authorized_devices'] += 1
                elif len(fields) == 2 and fields[1] == 'unauthorized':
                    result['unauthorized_devices'] += 1
            result['message'] = ('Android phone detected; DHU connection and video transport must be started'
                                 if result['authorized_devices'] else
                                 'No authorized Android phone is connected')
        except (OSError, subprocess.TimeoutExpired):
            result['message'] = 'ADB device query failed'
        return result

    def frame(self, kind='carplay'):
        if kind != 'carplay':
            raise ProjectionUnavailable('Android DHU does not expose a decoded frame endpoint')
        endpoint, token, _ = self._session()
        data = self._get(endpoint + '/api/mib-frame?token=' + token, 1048576)
        if len(data) < 4 or not data.startswith(b'\xff\xd8') or not data.endswith(b'\xff\xd9'):
            raise ProjectionUnavailable('Projection receiver did not supply a complete JPEG frame')
        return data

    @staticmethod
    def _send_ws(stream, payload, opcode=1):
        mask = os.urandom(4)
        size = len(payload)
        header = bytes([0x80 | opcode])
        if size < 126:
            header += bytes([0x80 | size])
        elif size <= 65535:
            header += bytes([0x80 | 126]) + struct.pack('!H', size)
        else:
            header += bytes([0x80 | 127]) + struct.pack('!Q', size)
        stream.sendall(header + mask + bytes(value ^ mask[i % 4] for i, value in enumerate(payload)))

    @staticmethod
    def _read_exact(stream, count):
        data = bytearray()
        while len(data) < count:
            chunk = stream.recv(count - len(data))
            if not chunk:
                raise ProjectionUnavailable('Projection control connection closed')
            data.extend(chunk)
        return bytes(data)

    def _exchange(self, messages):
        endpoint, token, _ = self._session()
        port = urllib.parse.urlsplit(endpoint).port
        try:
            with socket.create_connection(('127.0.0.1', port), timeout=self.timeout) as stream:
                key = base64.b64encode(os.urandom(16)).decode('ascii')
                request = (f'GET /ws?token={token} HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\n'
                           f'Upgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {key}\r\n'
                           'Sec-WebSocket-Version: 13\r\n\r\n')
                stream.sendall(request.encode('ascii'))
                # One byte per read avoids consuming bytes from the first WS frame.
                header = bytearray()
                while not header.endswith(b'\r\n\r\n'):
                    if len(header) > 16384:
                        raise ProjectionUnavailable('Invalid projection control handshake')
                    header.extend(self._read_exact(stream, 1))
                lines = header.decode('iso-8859-1').split('\r\n')
                headers = {line.split(':', 1)[0].lower(): line.split(':', 1)[1].strip()
                           for line in lines[1:] if ':' in line}
                expected = base64.b64encode(hashlib.sha1(
                    (key + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest()).decode()
                if ' 101 ' not in lines[0] or headers.get('sec-websocket-accept') != expected:
                    raise ProjectionUnavailable('Projection receiver rejected control connection')
                for message in messages:
                    self._send_ws(stream, json.dumps(message).encode('utf-8'))
                self._send_ws(stream, b'{"type":"ping"}')
                deadline = time.monotonic() + self.timeout
                while time.monotonic() < deadline:
                    first, second = self._read_exact(stream, 2)
                    opcode, size = first & 15, second & 127
                    if size == 126:
                        size = struct.unpack('!H', self._read_exact(stream, 2))[0]
                    elif size == 127:
                        size = struct.unpack('!Q', self._read_exact(stream, 8))[0]
                    if size > 2 * 1024 * 1024 or second & 128:
                        raise ProjectionUnavailable('Invalid projection control response')
                    payload = self._read_exact(stream, size)
                    if opcode == 9:
                        self._send_ws(stream, payload, 10)
                    elif opcode == 8:
                        raise ProjectionUnavailable('Projection receiver closed control connection')
                    elif opcode == 1:
                        data = json.loads(payload)
                        if isinstance(data, dict) and data.get('type') == 'pong':
                            self._send_ws(stream, struct.pack('!H', 1000), 8)
                            return
                raise ProjectionUnavailable('Projection control acknowledgement timed out')
        except (OSError, ValueError, UnicodeError):
            raise ProjectionUnavailable('Projection control connection failed') from None

    def action(self, kind, name):
        if kind != 'carplay':
            raise ProjectionUnavailable('Android DHU control transport is not connected')
        fields = {'up': {'wheel': -1}, 'down': {'wheel': 1},
                  'tilt_up': {'y': -127}, 'tilt_down': {'y': 127},
                  'tilt_left': {'x': -127}, 'tilt_right': {'x': 127},
                  'select': {'select': True}, 'back': {'back': True},
                  'menu': {'home': True}}
        if name not in fields:
            raise ValueError('Unsupported projection control')
        if not self.status(kind, refresh=True)['available']:
            raise ProjectionUnavailable('No active CarPlay phone session')
        self._exchange([{'type': 'knob', 'knob': fields[name]}, {'type': 'knob', 'knob': {}}])
        return {'sent': True, 'source': kind, 'action': name,
                'acknowledgement': 'receiver processed input; phone rendering not verified'}

    def touch(self, kind, x, y):
        if kind != 'carplay':
            raise ProjectionUnavailable('Android DHU control transport is not connected')
        if (isinstance(x, bool) or isinstance(y, bool)
                or not isinstance(x, (int, float)) or not isinstance(y, (int, float))
                or not math.isfinite(x) or not math.isfinite(y)
                or not (0 <= x <= 1 and 0 <= y <= 1)):
            raise ValueError('Touch coordinates must be normalized to 0..1')
        if not self.status(kind, refresh=True)['available']:
            raise ProjectionUnavailable('No active CarPlay phone session')
        self._exchange([{'type': 'touch', 'contacts': [{'id': 0, 'x': x, 'y': y, 'down': True}]},
                        {'type': 'touch', 'contacts': []}])
        return {'sent': True, 'source': kind}

    def close(self):
        """No receiver is owned by this adapter; never stop another app's session."""
