"""Android Auto through Google's Desktop Head Unit (DHU), capturing its video framebuffer.

adb and the DHU come from an installed Android SDK when present, otherwise
they are downloaded once from Google's SDK repository (checksums pinned) to
%LOCALAPPDATA%\\BMW-NBT-Emulator\\android-tools, outside the repository.
"""
import ctypes
from ctypes import wintypes as w
import hashlib
import io
import os
from pathlib import Path
import re
import shutil
import subprocess
import threading
import time
import urllib.request
import zipfile
from PIL import Image

SDK_REPOSITORY = 'https://dl.google.com/android/repository/'
# Same packages Android Studio installs: platform-tools and extras;google;auto.
DOWNLOADS = {
    'platform-tools': ('platform-tools_r37.0.1-win.zip', 'e03e78b1d80b396f1c3358e31251cb31740e1110',
                       'platform-tools/adb.exe'),
    'dhu': ('desktop-head-unit-windows-x64_r02.1.zip', 'c27bf84e59dda7b79315b6ca2a314063feffd6ac',
            'desktop-head-unit.exe'),
}
TOOLS = Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'BMW-NBT-Emulator/android-tools'
# The NBT display is 1280x480: the DHU renders 1280x720 video with 120 px
# margins above and below, so Android Auto lays out its wide 1280x480 UI.
WIDTH, HEIGHT, VIDEO_HEIGHT = 1280, 480, 720
LEGACY_ROOT = Path(r'G:\mibstd2-emulator\mib2emu')


def _sdk_roots():
    for name in ('NBT_ANDROID_SDK', 'ANDROID_HOME', 'ANDROID_SDK_ROOT'):
        if os.environ.get(name):
            yield Path(os.environ[name])
    if os.environ.get('LOCALAPPDATA'):
        yield Path(os.environ['LOCALAPPDATA']) / 'Android/Sdk'


def _download(name, report):
    """Fetch one SDK package into TOOLS/<name>, verifying Google's published SHA-1."""
    archive, sha1, member = DOWNLOADS[name]
    target = TOOLS / name
    if (target / member).is_file():
        return target / member
    report(f'Downloading {name} from Google (first use only)…')
    TOOLS.mkdir(parents=True, exist_ok=True)
    partial = TOOLS / (archive + '.part')
    digest = hashlib.sha1()
    with urllib.request.urlopen(SDK_REPOSITORY + archive, timeout=60) as response, open(partial, 'wb') as stream:
        while chunk := response.read(1 << 16):
            digest.update(chunk)
            stream.write(chunk)
    if digest.hexdigest() != sha1:
        partial.unlink()
        raise RuntimeError(f'{archive}: checksum mismatch, download discarded')
    temporary = TOOLS / (name + '.tmp')
    shutil.rmtree(temporary, ignore_errors=True)
    with zipfile.ZipFile(partial) as package:
        package.extractall(temporary)
    partial.unlink()
    shutil.rmtree(target, ignore_errors=True)
    temporary.rename(target)
    return target / member


def find_tools(report=lambda message: None):
    """(adb, dhu): installed Android SDK first, then the old mib2emu layout, else download."""
    adb = dhu = None
    for root in _sdk_roots():
        adb = adb or next((p for p in [root / 'platform-tools/adb.exe'] if p.is_file()), None)
        dhu = dhu or next((p for p in [root / 'extras/google/auto/desktop-head-unit.exe'] if p.is_file()), None)
    legacy_adb, legacy_dhu = LEGACY_ROOT / 'tools/platform-tools/adb.exe', LEGACY_ROOT / 'tools/dhu/desktop-head-unit.exe'
    adb = adb or (legacy_adb if legacy_adb.is_file() else None) or _download('platform-tools', report)
    dhu = dhu or (legacy_dhu if legacy_dhu.is_file() else None) or _download('dhu', report)
    return adb, dhu


def _content(image):
    """The 1280x480 Android Auto area of the DHU's 1280x720 video (margins cropped)."""
    if image.size != (WIDTH, VIDEO_HEIGHT):
        return image
    top = (VIDEO_HEIGHT - HEIGHT) // 2
    return image.crop((0, top, WIDTH, top + HEIGHT))


class AndroidSurface:
    def __init__(self, report=lambda message: None):
        self.report = report
        self.process = None
        self.hwnd = None
        self.message = 'Receiver stopped'
        self.lock = threading.RLock()
        self.screenshot_retry = 0
        self.video_focus = self.had_video_focus = False
        self.focus_checked = 0
        self.capture_path = Path(__file__).resolve().parents[3] / 'outputs/NBT_launcher/android-auto-frame.png'

    def start(self):
        adb, dhu = find_tools(self.report)
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
        # controller = true: the iDrive knob drives Android Auto's rotary (dpad) input.
        ini.write_text(f'[general]\ntouch = true\ncontroller = true\nresolution = {WIDTH}x{VIDEO_HEIGHT}\n'
                       f'marginheight = {VIDEO_HEIGHT - HEIGHT}\ndpi = 140\nframerate = 30\n'
                       '[sensors]\nlocation = true\nnight_mode = true\ndriving_status = true\n',encoding='utf-8')
        user = ctypes.WinDLL('user32')
        user.GetForegroundWindow.restype = w.HWND
        previous = user.GetForegroundWindow()
        self.process = subprocess.Popen([str(dhu),'-c',str(ini)],cwd=dhu.parent,stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                                        text=True,encoding='utf-8',errors='replace',
                                        creationflags=subprocess.CREATE_NO_WINDOW)
        process = self.process
        def drain():
            for line in process.stdout:
                self.message = line.strip()[:150]
                focus = re.search(r'Has video focus: (true|false)', line)
                if focus:
                    self.video_focus = focus.group(1) == 'true'
                    self.had_video_focus = self.had_video_focus or self.video_focus
        threading.Thread(target=drain,daemon=True).start()
        threading.Thread(target=self._tuck_window,args=(previous,),daemon=True).start()

    def _tuck_window(self, previous):
        """Move the DHU window off screen, out of the taskbar, and give the
        keyboard back to the viewer. It keeps rendering (screenshot and
        PrintWindow both still work); only the viewer shows Android Auto."""
        user = ctypes.WinDLL('user32')
        user.GetWindowLongW.argtypes = [w.HWND,ctypes.c_int]
        user.SetWindowLongW.argtypes = [w.HWND,ctypes.c_int,ctypes.c_long]
        user.SetWindowPos.argtypes = [w.HWND,w.HWND,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,w.UINT]
        user.ShowWindow.argtypes = [w.HWND,ctypes.c_int]
        user.SetForegroundWindow.argtypes = [w.HWND]
        deadline = time.monotonic()+20
        while time.monotonic() < deadline:
            hwnd = self._window()
            if hwnd:
                GWL_EXSTYLE, WS_EX_TOOLWINDOW, WS_EX_APPWINDOW = -20, 0x80, 0x40000
                style = user.GetWindowLongW(hwnd,GWL_EXSTYLE)
                user.ShowWindow(hwnd,0)            # re-shown below so the taskbar drops it
                user.SetWindowLongW(hwnd,GWL_EXSTYLE,(style | WS_EX_TOOLWINDOW) & ~WS_EX_APPWINDOW)
                user.SetWindowPos(hwnd,None,-32000,-32000,0,0,0x0001|0x0004|0x0010)  # NOSIZE|NOZORDER|NOACTIVATE
                user.ShowWindow(hwnd,4)            # SW_SHOWNOACTIVATE
                if previous:
                    user.SetForegroundWindow(previous)
                self.hwnd = hwnd
                return
            time.sleep(.05)

    def tap(self, x, y):
        """Touch at (x, y) of the 1280x480 Android Auto area."""
        with self.lock:
            if not self.process or self.process.poll() is not None:
                raise RuntimeError('Android Auto receiver is not running')
            self.process.stdin.write(f'tap {int(x)} {int(y) + (VIDEO_HEIGHT - HEIGHT) // 2}\n')
            self.process.stdin.flush()

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
            if time.monotonic() < self.screenshot_retry:
                return self._window_frame()
            before = self.capture_path.stat().st_mtime_ns if self.capture_path.exists() else 0
            self.process.stdin.write('screenshot ' + self.capture_path.as_posix() + '\n')
            self.process.stdin.flush()
            deadline = time.monotonic()+.4
            while time.monotonic()<deadline:
                try:
                    if self.capture_path.stat().st_mtime_ns != before:
                        with Image.open(self.capture_path) as image:
                            output=io.BytesIO()
                            _content(image.convert('RGB')).save(output,format='PPM')
                            return output.getvalue()
                except OSError:
                    pass
                time.sleep(.01)
            # No screenshot (the DHU reports no video focus at times): use the
            # window capture for a while instead of waiting on every frame.
            self.screenshot_retry = time.monotonic()+3
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
                image = _content(Image.frombytes('RGB',(width,height),pixels.raw,'raw','BGRX'))
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

    def exited(self):
        """True once Android Auto's own "Exit" was chosen: the phone then gives
        the screen back to the head unit (DHU video focus true -> false)."""
        with self.lock:
            if not self.process or self.process.poll() is not None:
                return False
            if time.monotonic() - self.focus_checked > 1:
                self.focus_checked = time.monotonic()
                self.process.stdin.write('focus video\n')
                self.process.stdin.flush()
        return self.had_video_focus and not self.video_focus

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
