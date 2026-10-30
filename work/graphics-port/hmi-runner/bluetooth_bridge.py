"""Real Windows Bluetooth transport reused from mib2emu; no BMW DSI binding yet."""
import ctypes
import json
import os
from pathlib import Path
import queue
import re
import subprocess
import sys
import threading


def radio_present():
    """Query a physical radio without inquiry, pairing, or system changes."""
    if os.name != 'nt':
        return False
    library = ctypes.WinDLL('bthprops.cpl', use_last_error=True)
    class Params(ctypes.Structure):
        _fields_ = [('size', ctypes.c_uint32)]
    library.BluetoothFindFirstRadio.argtypes = [ctypes.POINTER(Params), ctypes.POINTER(ctypes.c_void_p)]
    library.BluetoothFindFirstRadio.restype = ctypes.c_void_p
    library.BluetoothFindRadioClose.argtypes = [ctypes.c_void_p]
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    radio = ctypes.c_void_p()
    find = library.BluetoothFindFirstRadio(ctypes.byref(Params(ctypes.sizeof(Params))), ctypes.byref(radio))
    if not find:
        return False
    try:
        return bool(radio.value)
    finally:
        if radio.value:
            kernel.CloseHandle(radio)
        library.BluetoothFindRadioClose(find)


class BluetoothBridge:
    def __init__(self, mib_root=r'G:\mibstd2-emulator\mib2emu', python=None):
        self.script = Path(mib_root) / 'tools/btbridge.py'
        self.python = Path(python or sys.executable)
        self.process = None
        self.events = queue.Queue(maxsize=256)
        self._reader = None
        self._lock = threading.Lock()

    def status(self):
        present = radio_present()
        return {'radio_present': present, 'transport_installed': self.script.is_file(),
                'running': bool(self.process and self.process.poll() is None),
                'source': 'mib2emu_windows_bluetooth', 'original_hmi_integration': False,
                'profiles': ['A2DP sink', 'AVRCP media controls'],
                'hfp_pbap_supported': False,
                'message': 'Radio available' if present else 'No Windows Bluetooth radio detected'}

    def start(self):
        with self._lock:
            if self.process and self.process.poll() is None:
                return
            if not radio_present():
                raise RuntimeError('No Windows Bluetooth radio detected; connect or enable an adapter')
            if not self.script.is_file():
                raise RuntimeError('mib2emu Bluetooth transport is missing')
            self.process = subprocess.Popen(
                [str(self.python), '-u', str(self.script)], stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
                encoding='utf-8', creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            self._reader = threading.Thread(target=self._read, args=(self.process,), daemon=True)
            self._reader.start()

    def _read(self, process):
        try:
            for line in process.stdout:
                try:
                    event = json.loads(line)
                    if not isinstance(event, dict):
                        continue
                except ValueError:
                    continue
                # Bounded queue: stale metadata cannot consume unlimited memory.
                try:
                    self.events.put_nowait(event)
                except queue.Full:
                    try:
                        self.events.get_nowait()
                    except queue.Empty:
                        pass
                    try:
                        self.events.put_nowait(event)
                    except queue.Full:
                        pass
        except (OSError, ValueError):
            pass

    @staticmethod
    def validate(command):
        if not isinstance(command, dict):
            raise ValueError('Bluetooth command must be an object')
        name = command.get('cmd')
        allowed = {'paired': {'cmd'}, 'scan': {'cmd', 'seconds'},
                   'pair': {'cmd', 'addr'}, 'passkey_reply': {'cmd', 'accept'},
                   'connect': {'cmd', 'addr'}, 'disconnect': {'cmd'},
                   'control': {'cmd', 'what'}}
        if not isinstance(name, str) or name not in allowed or set(command) - allowed[name]:
            raise ValueError('Unknown Bluetooth command or fields')
        if name in {'pair', 'connect'} and not re.fullmatch(r'(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}', str(command.get('addr', ''))):
            raise ValueError('Bluetooth address must contain six hexadecimal octets')
        if name == 'scan':
            seconds = command.get('seconds', 10)
            if type(seconds) not in (int, float) or not 1 <= seconds <= 30:
                raise ValueError('Scan duration must be 1..30 seconds')
        if name == 'passkey_reply' and type(command.get('accept')) is not bool:
            raise ValueError('Pairing reply requires a boolean accept value')
        if name == 'control' and command.get('what') not in {'play', 'pause', 'next', 'previous'}:
            raise ValueError('Unknown media control')
        return dict(command)

    def send(self, command):
        command = self.validate(command)
        with self._lock:
            if not self.process or self.process.poll() is not None:
                raise RuntimeError('Bluetooth bridge is not running')
            self.process.stdin.write(json.dumps(command) + '\n')
            self.process.stdin.flush()

    def close(self):
        with self._lock:
            process, self.process = self.process, None
        if process:
            if process.stdin:
                process.stdin.close()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=3)
            if self._reader:
                self._reader.join(timeout=1)
            if process.stdout:
                process.stdout.close()


if __name__ == '__main__':
    print(json.dumps(BluetoothBridge().status(), indent=2))
