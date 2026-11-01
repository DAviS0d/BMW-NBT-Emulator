"""Wired CarPlay for the viewer: the bundled PlayPort receiver (work/carplay).

start() asks the iPhone for its CarPlay USB mode (usb_probe.py through the
UsbDk driver), enables IPv6 on the iPhone's USB network adapter if Windows has
it off (an administrator prompt, once per adapter), then starts the PlayPort
server bound to that adapter and a browser that decodes the video and plays
CarPlay audio. The browser window is kept off screen; the viewer shows the
decoded frames. Requires Java 21+, Apple Mobile Device Support, UsbDk and
Edge or Chrome.
"""
import base64
import ctypes
from ctypes import wintypes as w
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import struct
import subprocess
import sys
import threading
import time

from projection_bridge import ProjectionBridge, ProjectionUnavailable

CARPLAY = Path(__file__).resolve().parents[2] / 'carplay'
PLAYPORT = CARPLAY / 'playport'
USB_SCRIPTS = CARPLAY / 'carplay-windows'
STATE = Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'BMW-NBT-Emulator/carplay'
WIDTH, HEIGHT = 1280, 480
NO_WINDOW = subprocess.CREATE_NO_WINDOW
BROWSERS = (r'%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe',
            r'%ProgramFiles%\Microsoft\Edge\Application\msedge.exe',
            r'%ProgramFiles%\Google\Chrome\Application\chrome.exe',
            r'%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe')


def _powershell(command, timeout=30):
    result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', command],
                            capture_output=True, text=True, timeout=timeout, creationflags=NO_WINDOW)
    return result.stdout.strip()


def iphone():
    """Instance id of the one attached iPhone (USB composite device)."""
    found = _powershell(r"Get-PnpDevice -PresentOnly | Where-Object { $_.InstanceId -match "
                        r"'^USB\\VID_05AC&PID_12[0-9A-Fa-f]{2}\\[^&]+$' } | ForEach-Object InstanceId").splitlines()
    if len(found) != 1:
        raise ProjectionUnavailable('Connect one unlocked iPhone by USB and accept "Trust this computer".')
    return found[0]


# The iPhone's CDC NCM (USB network) function, present once CarPlay USB mode is on.
NCM = "Get-NetAdapter | Where-Object { $_.PnPDeviceID -match 'VID_05AC.*CDC_0D' -and $_.Status -eq 'Up' }"


def ncm_adapter():
    """(ifIndex, IPv6 link-local or None) of the iPhone's USB network adapter, or None."""
    script = (f"$a = {NCM} | Select-Object -First 1; if ($a) {{ $ip = Get-NetIPAddress -InterfaceIndex $a.ifIndex "
              "-AddressFamily IPv6 -ErrorAction SilentlyContinue | Where-Object { $_.IPAddress -like 'fe80*' } | "
              "Select-Object -First 1; \"$($a.ifIndex) $($ip.IPAddress)\" }")
    fields = _powershell(script).split()
    if not fields:
        return None
    return int(fields[0]), (fields[1].split('%')[0] + '%' + fields[0] if len(fields) > 1 else None)


def ncm_address(device=None):
    """IPv6 link-local address%scope of the iPhone's USB network adapter, or None."""
    adapter = ncm_adapter()
    return adapter[1] if adapter else None


def enable_carplay_mode():
    """Ask the iPhone for its CarPlay USB mode (vendor request through UsbDk,
    no administrator rights); it re-enumerates with its NCM network function."""
    result = subprocess.run([sys.executable, '-I', str(USB_SCRIPTS / 'usb_probe.py'), '--usbdk', '--enable-carplay'],
                            capture_output=True, text=True, timeout=30, creationflags=NO_WINDOW)
    if 'CarPlay mode request accepted' not in result.stdout:
        detail = (result.stderr or result.stdout).strip().splitlines()[-1:] or ['no response']
        if 'UsbDk' in detail[0]:
            raise ProjectionUnavailable('CarPlay over USB needs the UsbDk driver: '
                                        'https://github.com/daynix/UsbDk/releases (UsbDk_1.0.22_x64.msi).')
        raise ProjectionUnavailable('The iPhone refused CarPlay USB mode: ' + detail[0])


def enable_ipv6():
    """Wired CarPlay runs over IPv6: enable it on the iPhone adapter only (administrator prompt)."""
    command = (f"$p = Start-Process powershell.exe -Verb RunAs -WindowStyle Hidden -Wait -PassThru -ArgumentList "
               f"'-NoProfile','-Command','{NCM.replace(chr(39), chr(39) * 2)} | Enable-NetAdapterBinding -ComponentID ms_tcpip6'; "
               "exit $p.ExitCode")
    result = subprocess.run(['powershell.exe', '-NoProfile', '-Command', command], capture_output=True, text=True,
                            timeout=180, creationflags=NO_WINDOW)
    if result.returncode:
        raise ProjectionUnavailable('IPv6 on the iPhone USB adapter was not enabled (administrator prompt declined).')


def java():
    home = os.environ.get('JAVA_HOME')
    candidates = [Path(home) / 'bin/java.exe'] if home else []
    candidates += [Path(p) for p in [shutil.which('java')] if p]
    for candidate in candidates:
        if candidate.is_file():
            version = subprocess.run([str(candidate), '-version'], capture_output=True, text=True,
                                     creationflags=NO_WINDOW).stderr
            match = re.search(r'version "(\d+)', version)
            if match and int(match.group(1)) >= 21:
                return candidate
    raise ProjectionUnavailable('CarPlay needs Java 21 or newer (for example Eclipse Temurin 21).')


def browser():
    for path in BROWSERS:
        candidate = Path(os.path.expandvars(path))
        if candidate.is_file():
            return candidate
    raise ProjectionUnavailable('CarPlay needs Microsoft Edge or Google Chrome to decode the video.')


def _free_port():
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        return probe.getsockname()[1]


def _windows_of(pid):
    user = ctypes.WinDLL('user32')
    callback = ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
    user.GetWindowThreadProcessId.argtypes = [w.HWND, ctypes.POINTER(w.DWORD)]
    user.IsWindowVisible.argtypes = [w.HWND]
    user.EnumWindows.argtypes = [callback, w.LPARAM]
    found = []

    @callback
    def visit(hwnd, _):
        owner = w.DWORD()
        user.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid and user.IsWindowVisible(hwnd):
            found.append(hwnd)
        return True
    user.EnumWindows(visit, 0)
    return found


def _tuck(pid, previous, seconds=20):
    """Off screen and out of the taskbar, keyboard back to the viewer (as for the Android DHU)."""
    user = ctypes.WinDLL('user32')
    user.GetWindowLongW.argtypes = [w.HWND, ctypes.c_int]
    user.SetWindowLongW.argtypes = [w.HWND, ctypes.c_int, ctypes.c_long]
    user.SetWindowPos.argtypes = [w.HWND, w.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, w.UINT]
    user.ShowWindow.argtypes = [w.HWND, ctypes.c_int]
    user.SetForegroundWindow.argtypes = [w.HWND]
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        windows = _windows_of(pid)
        if windows:
            for hwnd in windows:
                style = user.GetWindowLongW(hwnd, -20)
                user.ShowWindow(hwnd, 0)
                user.SetWindowLongW(hwnd, -20, (style | 0x80) & ~0x40000)   # TOOLWINDOW, not APPWINDOW
                user.SetWindowPos(hwnd, None, -32000, -32000, 0, 0, 0x0001 | 0x0004 | 0x0010)
                user.ShowWindow(hwnd, 4)
            if previous:
                user.SetForegroundWindow(previous)
            return
        time.sleep(.05)


class CarPlayReceiver(ProjectionBridge):
    def __init__(self, report=lambda message: None):
        super().__init__(timeout=2.0)
        self.report = report
        self.server = self.viewer = None
        self.endpoint = self.token = None
        self.pin = None
        self.lines = []
        self.control = None
        self.control_lock = threading.RLock()
        self.last_frame = None
        self.ui_requested = False

    def _session(self):
        if not self.endpoint:
            raise ProjectionUnavailable('CarPlay receiver is not running')
        return self.endpoint, self.token, 'usb'

    def start(self, timeout=120):
        java_exe, browser_exe = java(), browser()
        iphone()
        adapter = ncm_adapter()
        if not adapter:
            self.report('Switching the iPhone to CarPlay USB mode…')
            enable_carplay_mode()
            deadline = time.monotonic() + 30
            while not adapter and time.monotonic() < deadline:
                time.sleep(1)
                adapter = ncm_adapter()
            if not adapter:
                raise ProjectionUnavailable('The iPhone USB network did not appear; unplug and reconnect the cable.')
        address = adapter[1]
        if not address:
            time.sleep(3)          # link-local configuration takes a moment after enumeration
            address = ncm_address()
        if not address:
            self.report('Approve the Windows administrator prompt to enable IPv6 on the iPhone USB adapter…')
            enable_ipv6()
            deadline = time.monotonic() + 20
            while not address and time.monotonic() < deadline:
                time.sleep(1)
                address = ncm_address()
            if not address:
                raise ProjectionUnavailable('The iPhone USB adapter has no IPv6 address; reconnect the cable.')
        STATE.mkdir(parents=True, exist_ok=True)
        port, self.token = _free_port(), secrets.token_hex(16)
        library = PLAYPORT / 'server/build/install/server/lib'
        command = [str(java_exe), '-Dorg.slf4j.simpleLogger.defaultLogLevel=info', '-cp', str(library / '*'),
                   'com.playport.server.MainKt', '--wired', '--http', '--bind', address,
                   '--http-port', str(port), '--token', self.token, '--device-name', 'BMW NBT',
                   # Label and icon of the phone's car (OEM) button.
                   '--oem-label', 'BMW', '--oem-icon', str(CARPLAY / 'carplay-assets/bmw.png'),
                   '--width', str(WIDTH), '--height', str(HEIGHT),
                   '--identity-dir', str(CARPLAY / 'identity'), '--state-dir', str(STATE),
                   '--usb-python', sys.executable, '--usb-helper', str(USB_SCRIPTS / 'usb_carkit.py')]
        self.report('Starting the CarPlay receiver…')
        self.server = subprocess.Popen(command, cwd=PLAYPORT, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                       stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace',
                                       creationflags=NO_WINDOW)
        threading.Thread(target=self._drain, daemon=True).start()
        self.endpoint = f'http://127.0.0.1:{port}'
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline and self.server.poll() is None:
            try:
                self._get(self.endpoint + '/api/status', 65536)
                break
            except ProjectionUnavailable:
                time.sleep(.3)
        if self.server.poll() is not None:
            raise ProjectionUnavailable('CarPlay receiver stopped: ' + ' | '.join(self.lines[-4:]))
        user = ctypes.WinDLL('user32')
        user.GetForegroundWindow.restype = w.HWND
        previous = user.GetForegroundWindow()
        profile = STATE / 'browser'
        self.viewer = subprocess.Popen([str(browser_exe), f'--user-data-dir={profile}', '--no-first-run',
                                        '--no-default-browser-check', '--autoplay-policy=no-user-gesture-required',
                                        '--window-position=-32000,-32000', f'--window-size={WIDTH},{HEIGHT}',
                                        '--disable-background-timer-throttling', '--disable-renderer-backgrounding',
                                        '--disable-backgrounding-occluded-windows',
                                        f'--app={self.endpoint}/?token={self.token}&mib=1'],
                                       creationflags=NO_WINDOW)
        threading.Thread(target=_tuck, args=(self.viewer.pid, previous), daemon=True).start()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.server.poll() is not None:
                raise ProjectionUnavailable('CarPlay receiver stopped: ' + ' | '.join(self.lines[-4:]))
            if self.status('carplay', refresh=True)['available']:
                return
            self.report(f'Unlock the iPhone and accept CarPlay (PIN {self.pin or "shown on the phone"})…')
            time.sleep(1)
        raise ProjectionUnavailable('No CarPlay session from the iPhone: ' + ' | '.join(self.lines[-3:]))

    def _drain(self):
        for line in self.server.stdout:
            line = line.rstrip()
            match = re.search(r'Pairing PIN\s*:\s*(\d+)', line)
            if match:
                self.pin = match.group(1)
            if 'airplay command type=requestUI' in line:
                self.ui_requested = True    # the phone's BMW (OEM) button: back to the head unit
            if line:
                self.lines = (self.lines + [line[:200]])[-50:]

    def _control(self):
        """One WebSocket kept open for input. PlayPort treats every new socket as
        a viewer joining and asks the phone for a keyframe, which blanked the
        picture for about a second when each key opened its own connection."""
        if self.control:
            return self.control
        port = int(self.endpoint.rsplit(':', 1)[1])
        stream = socket.create_connection(('127.0.0.1', port), timeout=self.timeout)
        key = base64.b64encode(os.urandom(16)).decode('ascii')
        stream.sendall((f'GET /ws?token={self.token} HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\n'
                        f'Upgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {key}\r\n'
                        'Sec-WebSocket-Version: 13\r\n\r\n').encode('ascii'))
        header = bytearray()
        while not header.endswith(b'\r\n\r\n'):
            if len(header) > 16384:
                raise ProjectionUnavailable('Invalid projection control handshake')
            header.extend(self._read_exact(stream, 1))
        expected = base64.b64encode(hashlib.sha1(
            (key + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest()).decode()
        if b' 101 ' not in header.split(b'\r\n', 1)[0] or expected.encode() not in header:
            stream.close()
            raise ProjectionUnavailable('Projection receiver rejected control connection')
        stream.settimeout(None)
        self.control = stream
        threading.Thread(target=self._discard, args=(stream,), daemon=True).start()
        return stream

    def _discard(self, stream):
        """Read and drop what the server broadcasts to viewers (video, audio, status)."""
        try:
            while True:
                first, second = self._read_exact(stream, 2)
                size = second & 127
                if size == 126:
                    size = struct.unpack('!H', self._read_exact(stream, 2))[0]
                elif size == 127:
                    size = struct.unpack('!Q', self._read_exact(stream, 8))[0]
                if first & 15 in (8, 9):
                    payload = self._read_exact(stream, size)
                else:
                    while size:
                        chunk = stream.recv(min(size, 65536))
                        if not chunk:
                            raise ProjectionUnavailable('Projection control connection closed')
                        size -= len(chunk)
                if first & 15 == 9:
                    with self.control_lock:
                        self._send_ws(stream, payload, 10)
                elif first & 15 == 8:
                    break
        except (OSError, ProjectionUnavailable, ValueError):
            pass
        with self.control_lock:
            if self.control is stream:
                self.control = None
        stream.close()

    def _send(self, *messages):
        with self.control_lock:
            for attempt in range(2):
                try:
                    stream = self._control()
                    for message in messages:
                        self._send_ws(stream, json.dumps(message).encode('utf-8'))
                    return
                except OSError:
                    if self.control:
                        self.control.close()
                    self.control = None
            raise ProjectionUnavailable('Projection control connection failed')

    def action(self, kind, name):
        fields = {'up': {'wheel': -1}, 'down': {'wheel': 1},
                  'tilt_up': {'y': -127}, 'tilt_down': {'y': 127},
                  'tilt_left': {'x': -127}, 'tilt_right': {'x': 127},
                  'select': {'select': True}, 'back': {'back': True}, 'menu': {'home': True}}
        if name in fields:
            self._send({'type': 'knob', 'knob': fields[name]}, {'type': 'knob', 'knob': {}})

    def tap(self, x, y):
        """Touch at (x, y) of the WIDTH x HEIGHT CarPlay frame. Like PlayPort's
        browser client, the release is the same contact with down=false."""
        point = {'id': 0, 'x': min(1, max(0, x / WIDTH)), 'y': min(1, max(0, y / HEIGHT))}
        self._send({'type': 'touch', 'contacts': [{**point, 'down': True}]})
        time.sleep(.05)
        self._send({'type': 'touch', 'contacts': [{**point, 'down': False}]})

    def exited(self):
        """True once the BMW button in CarPlay was pressed (the phone sends requestUI)."""
        return self.ui_requested

    def frame(self, kind='carplay'):
        """Latest decoded frame; the previous one while the browser decoder
        catches up (a keyframe or a short stall), instead of an error."""
        try:
            self.last_frame = super().frame(kind)
        except ProjectionUnavailable:
            if not self.last_frame or not self.server or self.server.poll() is not None:
                raise
        return self.last_frame

    def close(self):
        with self.control_lock:
            if self.control:
                self.control.close()
                self.control = None
        for process in (self.viewer, self.server):
            if process and process.poll() is None:
                # The server's USB helper and the browser's helpers are child processes.
                subprocess.run(['taskkill', '/T', '/F', '/PID', str(process.pid)], capture_output=True,
                               creationflags=NO_WINDOW)
        self.viewer = self.server = None
        self.endpoint = None


if __name__ == '__main__':
    receiver = CarPlayReceiver(report=print)
    try:
        receiver.start()
        print(json.dumps(receiver.status('carplay', refresh=True), indent=2))
        frame = receiver.frame('carplay')
        print('frame bytes', len(frame))
        input('CarPlay running; press Enter to stop.')
    finally:
        receiver.close()
