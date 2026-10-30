# © 2026 davisod & JEtsKi
"""Manage the native renderer's localhost connection without a Python data relay."""
import json
import os
from pathlib import Path
import re
import subprocess
import threading
import time
from stdio_socket_bridge import SocketRendererBridge


class NativeSocketRendererBridge(SocketRendererBridge):
    def start(self, connect_timeout=10):
        if not self.renderer.is_file():
            raise FileNotFoundError(self.renderer)
        if self.capture:
            raise ValueError('Native socket mode does not capture the protocol stream')
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.connected = threading.Event()
        self.native_counts_seen = False
        self.native_socket_counts = (0, 0)
        self.native_dma_counts = (0, 0)
        env = os.environ.copy()
        if self.dll_dir:
            env['PATH'] = str(self.dll_dir)+os.pathsep+env.get('PATH', '')
        env.update({str(k):str(v) for k,v in self.extra_env.items()})
        env['GLHOST_QEMU_PORT'] = str(self.port)
        # stdin is only a lifetime-control pipe. Its EOF wakes the native socket
        # reader so the original renderer cleanup and exit can complete.
        self.process = subprocess.Popen(self.command, cwd=self.renderer.parent,
            stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            bufsize=0, env=env, creationflags=subprocess.CREATE_NO_WINDOW)
        self.started = time.monotonic()
        thread = threading.Thread(target=self._stderr, name='native-renderer-stderr', daemon=True)
        self.threads.append(thread)
        thread.start()
        try:
            deadline = time.monotonic()+connect_timeout
            while not self.connected.wait(.05):
                if self.process.poll() is not None or time.monotonic() >= deadline:
                    raise RuntimeError('Native renderer did not connect; see '+str(self.log_dir/'renderer-stderr.log'))
        except BaseException:
            self.stop()
            raise
        return self

    def _stderr(self):
        pending = b''
        try:
            with (self.log_dir/'renderer-stderr.log').open('wb') as output:
                while True:
                    block = os.read(self.process.stderr.fileno(), 65536)
                    if not block:
                        break
                    output.write(block)
                    output.flush()
                    pending += block
                    lines = pending.split(b'\n')
                    pending = lines.pop()
                    for line in lines:
                        if b'GLHOST_NATIVE_SOCKET_CONNECTED port=' in line:
                            self.connected.set()
                        match = re.search(rb'GLHOST_NATIVE_SOCKET_COUNTS rx=(\d+) tx=(\d+)', line)
                        if match:
                            self.native_socket_counts = (int(match[1]), int(match[2]))
                            self.guest_to_renderer = self.native_socket_counts[0]+self.native_dma_counts[0]
                            self.renderer_to_guest = self.native_socket_counts[1]+self.native_dma_counts[1]
                            self.native_counts_seen = True
                        match = re.search(rb'GLHOST_DMA_COUNTS rx=(\d+) tx=(\d+)', line)
                        if match:
                            self.native_dma_counts = (int(match[1]), int(match[2]))
                            self.guest_to_renderer = self.native_socket_counts[0]+self.native_dma_counts[0]
                            self.renderer_to_guest = self.native_socket_counts[1]+self.native_dma_counts[1]
        except (OSError, ValueError) as error:
            self._record_error('native-renderer-stderr', error)

    def stop(self):
        result = super().stop()
        result['kind'] = 'NATIVE_LOCALHOST_RENDERER_CONNECTION'
        if 'GLHOST_DMA_CONFIG' in self.extra_env:
            result['kind'] = 'BOUNDED_GUEST_DMA_RENDERER_CONNECTION'
            result['dma_counts'] = self.native_dma_counts
        result['protocol_capture_enabled'] = False
        result['native_byte_counts_seen'] = getattr(self, 'native_counts_seen', False)
        if self.log_dir.exists():
            (self.log_dir/'relay-result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        return result
