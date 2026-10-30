"""Reuse the installed Android Auto DHU, capturing only our owned receiver window."""
import ctypes
from ctypes import wintypes as w
import io
from pathlib import Path
import subprocess
import threading
import time
from PIL import Image


class AndroidSurface:
    def __init__(self, mib_root=r'G:\mibstd2-emulator\mib2emu'):
        self.root = Path(mib_root)
        self.process = None
        self.hwnd = None
        self.message = 'Receiver stopped'
        self.lock = threading.RLock()
        self.capture_path = Path(__file__).resolve().parents[3] / 'outputs/NBT_launcher/android-auto-frame.png'

    def start(self):
        adb = self.root / 'tools/platform-tools/adb.exe'
        dhu = self.root / 'tools/dhu/desktop-head-unit.exe'
        result = subprocess.run([str(adb),'devices'], capture_output=True, text=True, timeout=10,
                                creationflags=subprocess.CREATE_NO_WINDOW)
        devices = [line.split()[0] for line in result.stdout.splitlines()[1:] if line.strip().endswith('\tdevice')]
        if not devices:
            raise RuntimeError('Connect an authorized Android phone over USB or wireless ADB and start its Android Auto head-unit server.')
        forward = subprocess.run([str(adb),'-s',devices[0],'forward','tcp:5277','tcp:5277'],
                                 capture_output=True,text=True,timeout=10,creationflags=subprocess.CREATE_NO_WINDOW)
        if forward.returncode:
            raise RuntimeError('Could not forward the Android Auto head-unit server on port 5277')
        ini = Path(__file__).resolve().parents[3] / 'outputs/NBT_launcher/android-auto.ini'
        ini.parent.mkdir(parents=True, exist_ok=True)
        ini.write_text('[general]\ntouch = true\nresolution = 800x480\ndpi = 140\nframerate = 30\n[sensors]\nlocation = true\nnight_mode = true\ndriving_status = true\n',encoding='utf-8')
        self.process = subprocess.Popen([str(dhu),'-c',str(ini)],cwd=dhu.parent,stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                                        text=True,encoding='utf-8',errors='replace',
                                        creationflags=subprocess.CREATE_NO_WINDOW)
        process = self.process
        def drain():
            for line in process.stdout:
                self.message = line.strip()[:150]
        threading.Thread(target=drain,daemon=True).start()

    def _window(self):
        if not self.process or self.process.poll() is not None:
            return None
        user = ctypes.WinDLL('user32',use_last_error=True)
        callback = ctypes.WINFUNCTYPE(w.BOOL,w.HWND,w.LPARAM)
        user.GetWindowThreadProcessId.argtypes = [w.HWND,ctypes.POINTER(w.DWORD)]
        user.IsWindowVisible.argtypes = [w.HWND]
        user.EnumWindows.argtypes = [callback,w.LPARAM]
        found = []
        @callback
        def visit(hwnd, _):
            pid = w.DWORD()
            user.GetWindowThreadProcessId(hwnd,ctypes.byref(pid))
            if pid.value == self.process.pid and user.IsWindowVisible(hwnd):
                found.append(hwnd)
            return True
        user.EnumWindows(visit,0)
        return found[0] if found else None

    def frame(self):
        # The official DHU can export its actual video framebuffer directly.
        # Prefer that over PrintWindow, which can return black for SDL/OpenGL.
        with self.lock:
            if not self.process or self.process.poll() is not None:
                return None
            before = self.capture_path.stat().st_mtime_ns if self.capture_path.exists() else 0
            self.process.stdin.write('screenshot ' + self.capture_path.as_posix() + '\n')
            self.process.stdin.flush()
            deadline = time.monotonic()+.4
            while time.monotonic()<deadline:
                try:
                    if self.capture_path.stat().st_mtime_ns != before:
                        with Image.open(self.capture_path) as image:
                            output=io.BytesIO()
                            image.convert('RGB').save(output,format='PPM')
                            return output.getvalue()
                except OSError:
                    pass
                time.sleep(.01)
        return self._window_frame()

    def _window_frame(self):
        with self.lock:
            hwnd = self._window()
            if not hwnd:
                return None
            user, gdi = ctypes.WinDLL('user32'),ctypes.WinDLL('gdi32')
            user.GetClientRect.argtypes = [w.HWND,ctypes.POINTER(w.RECT)]
            user.GetDC.argtypes, user.GetDC.restype = [w.HWND],w.HDC
            user.ReleaseDC.argtypes = [w.HWND,w.HDC]
            user.PrintWindow.argtypes = [w.HWND,w.HDC,w.UINT]
            gdi.CreateCompatibleDC.argtypes,gdi.CreateCompatibleDC.restype = [w.HDC],w.HDC
            gdi.CreateCompatibleBitmap.argtypes,gdi.CreateCompatibleBitmap.restype = [w.HDC,ctypes.c_int,ctypes.c_int],w.HBITMAP
            gdi.SelectObject.argtypes,gdi.SelectObject.restype = [w.HDC,w.HANDLE],w.HANDLE
            gdi.DeleteObject.argtypes = [w.HANDLE]
            gdi.DeleteDC.argtypes = [w.HDC]
            gdi.GetDIBits.argtypes = [w.HDC,w.HBITMAP,w.UINT,w.UINT,ctypes.c_void_p,ctypes.c_void_p,w.UINT]
            rect = w.RECT()
            user.GetClientRect(hwnd,ctypes.byref(rect))
            width,height = rect.right,rect.bottom
            if not 0 < width <= 4096 or not 0 < height <= 2160:
                return None
            dc = user.GetDC(hwnd)
            memory = gdi.CreateCompatibleDC(dc)
            bitmap = gdi.CreateCompatibleBitmap(dc,width,height)
            previous = gdi.SelectObject(memory,bitmap)
            try:
                if not user.PrintWindow(hwnd,memory,3):
                    return None
                header = ctypes.create_string_buffer(40)
                import struct
                struct.pack_into('<IiiHHIIiiII',header,0,40,width,-height,1,32,0,width*height*4,0,0,0,0)
                pixels = ctypes.create_string_buffer(width*height*4)
                if not gdi.GetDIBits(memory,bitmap,0,height,pixels,header,0):
                    return None
                image = Image.frombytes('RGB',(width,height),pixels.raw,'raw','BGRX')
                output = io.BytesIO()
                image.save(output,format='PPM')
                return output.getvalue()
            finally:
                gdi.SelectObject(memory,previous)
                gdi.DeleteObject(bitmap)
                gdi.DeleteDC(memory)
                user.ReleaseDC(hwnd,dc)

    def action(self,name):
        commands = {'up':'dpad rotate left','down':'dpad rotate right','tilt_left':'dpad left','tilt_right':'dpad right',
                    'tilt_up':'dpad up','tilt_down':'dpad down','select':'dpad click','back':'dpad back'}
        if name not in commands:
            return
        with self.lock:
            if not self.process or self.process.poll() is not None:
                raise RuntimeError('Android Auto receiver is not running')
            self.process.stdin.write(commands[name]+'\n')
            self.process.stdin.flush()

    def status(self):
        return {'running':bool(self.process and self.process.poll() is None),'message':self.message}

    def close(self):
        with self.lock:
            if self.process:
                if self.process.stdin:
                    self.process.stdin.close()
                try:
                    self.process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self.process.terminate()
                    self.process.wait(timeout=3)
