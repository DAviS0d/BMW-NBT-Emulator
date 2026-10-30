"""Local browser display and native controls for the original NBT emulator."""
import ctypes
import json
import re
import struct
import subprocess
import sys
import threading
import time
import zlib
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from vehicle_sim import VehicleSimulator

HERE = Path(__file__).resolve().parent
ACTIONS = {'up', 'down', 'select', 'back', 'menu', 'option', 'tilt_left',
           'tilt_right', 'tilt_up', 'tilt_down', 'radio', 'media', 'nav', 'tel', 'stop'}
LOCK = threading.Lock()
STARTED = 0
FRAME_CACHE = (None, None)
VEHICLE = VehicleSimulator()


def read_json(path):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def alive(pid):
    if not pid:
        return False
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
    kernel.OpenProcess.restype = ctypes.c_void_p
    kernel.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)]
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel.OpenProcess(0x1000, False, pid)
    if not handle:
        return False
    try:
        code = ctypes.c_uint32()
        return bool(kernel.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == 259
    finally:
        kernel.CloseHandle(handle)


def current():
    for folder in sorted((HERE / 'runs').glob('run-*'), reverse=True):
        info = read_json(folder / 'run-info.json')
        if (not (folder / 'result.json').exists()
                and alive(info.get('owner_pid')) and alive(info.get('qemu_pid'))):
            return folder, info
    return None, {}


def status():
    folder, info = current()
    ready = False
    if folder:
        try:
            events = (folder / 'controller-events.jsonl').read_text(encoding='utf-8')
            ready = '"kind": "controller_configured"' in events
        except OSError:
            pass
    frame = bool(folder and (folder / 'frame.ppm').exists())
    return {'running': bool(folder), 'starting': not folder and time.monotonic() - STARTED < 45,
            'ready': ready, 'frame': frame, 'accelerator': info.get('cpu_accelerator'),
            'run': folder.name if folder else None}


def start():
    global STARTED
    with LOCK:
        if current()[0] or time.monotonic() - STARTED < 45:
            return
        python = viewer_python().with_name('pythonw.exe')
        native = HERE.parents[1] / 'bridge-v2/ifs/walthread_keyboard_dma_v2_native.ifs'
        arguments = ['--native'] if native.exists() else []
        subprocess.Popen([str(python), str(HERE / 'viewer.py'), *arguments], cwd=HERE,
                         creationflags=subprocess.CREATE_NO_WINDOW)
        STARTED = time.monotonic()


def viewer_python():
    """Prefer an installed 64-bit interpreter for fast firmware hashing/loading."""
    if struct.calcsize('P') == 8:
        return Path(sys.executable)
    root = Path(os.environ.get('LOCALAPPDATA', '')) / 'Programs/Python'
    for candidate in sorted(root.glob('Python*/python.exe'), reverse=True):
        try:
            result = subprocess.run(
                [str(candidate), '-c', 'import struct, tkinter; print(struct.calcsize("P"))'],
                capture_output=True, text=True, timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW)
            if result.returncode == 0 and result.stdout.strip() == '8':
                return candidate
        except (OSError, subprocess.TimeoutExpired):
            continue
    return Path(sys.executable)


def action(name):
    if not isinstance(name, str) or name not in ACTIONS:
        raise ValueError('Unknown control')
    with LOCK:
        folder, _ = current()
        if not folder:
            raise ValueError('The emulator is not running')
        if name != 'stop' and not status()['ready']:
            raise ValueError('Controls are still initializing')
        with (folder / 'controller-actions.jsonl').open('a', encoding='utf-8') as stream:
            stream.write(json.dumps({'action': name}) + '\n')


def png_frame():
    global FRAME_CACHE
    folder, _ = current()
    if not folder:
        return None
    path = folder / 'frame.ppm'
    extension=read_json(folder/'extension-state.json')
    if extension.get('active') and extension.get('ready'):
        path=folder/'extension-frame.ppm'
    try:
        stamp = (str(path), path.stat().st_mtime_ns)
        if FRAME_CACHE[0] == stamp:
            return FRAME_CACHE[1]
        data = path.read_bytes()
        match = re.match(rb'P6\s+(\d+)\s+(\d+)\s+255\s', data)
        if not match:
            return None
        width, height = map(int, match.groups())
        pixels = data[match.end():]
        if not (0 < width <= 4096 and 0 < height <= 4096) or len(pixels) != width * height * 3:
            return None
        def chunk(kind, payload):
            return struct.pack('>I', len(payload)) + kind + payload + struct.pack('>I', zlib.crc32(kind + payload))
        rows = b''.join(b'\0' + pixels[i:i+width*3] for i in range(0, len(pixels), width*3))
        png = (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0))
               + chunk(b'IDAT', zlib.compress(rows, 1)) + chunk(b'IEND', b''))
        FRAME_CACHE = stamp, png
        return png
    except OSError:
        return None


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send(self, code, data, kind='application/json'):
        self.send_response(code)
        self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        route = self.path.split('?')[0]
        if route == '/':
            self.send(200, (HERE / 'webui.html').read_bytes(), 'text/html; charset=utf-8')
        elif route == '/api/status':
            self.send(200, json.dumps(status()).encode())
        elif route == '/api/vehicle':
            self.send(200, json.dumps(VEHICLE.snapshot()).encode())
        elif route == '/api/frame':
            data = png_frame()
            self.send(200 if data else 204, data or b'', 'image/png')
        else:
            self.send(404, b'{}')

    def do_POST(self):
        # Only the page served by this local server may send controls.
        host = self.headers.get('Host')
        if host not in {'127.0.0.1:8877', 'localhost:8877'} or self.headers.get('Origin') not in {None, 'http://' + host}:
            self.send(403, b'{}')
            return
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 <= size <= 1024:
                raise ValueError('Request too large')
            body = json.loads(self.rfile.read(size) or b'{}')
            if not isinstance(body, dict):
                raise ValueError('Request body must be a JSON object')
            if self.path == '/api/start':
                start()
            elif self.path == '/api/action':
                action(body.get('action'))
            elif self.path == '/api/vehicle':
                state = VEHICLE.update(body)
                self.send(200, json.dumps(state).encode())
                return
            elif self.path == '/api/vehicle/demo':
                if type(body.get('enabled')) is not bool:
                    raise ValueError('enabled must be true or false')
                state = VEHICLE.start_demo() if body['enabled'] else VEHICLE.stop_demo()
                self.send(200, json.dumps(state).encode())
                return
            else:
                self.send(404, b'{}')
                return
            self.send(200, b'{"ok":true}')
        except (ValueError, OSError) as error:
            self.send(400, json.dumps({'error': str(error)}).encode())


if __name__ == '__main__':
    server = ThreadingHTTPServer(('127.0.0.1', 8877), Handler)
    print('NBT Web UI: http://127.0.0.1:8877', flush=True)
    try:
        server.serve_forever()
    finally:
        VEHICLE.close()
        server.server_close()
