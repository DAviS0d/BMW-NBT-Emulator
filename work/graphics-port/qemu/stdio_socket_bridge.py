# © 2026 davisod & JEtsKi
"""Binary full-duplex QEMU socket-chardev <-> renderer stdin/stdout relay.

The relay does not interpret, fabricate or render GL commands. It preserves the
upstream guest record stream and returns the renderer's actual bytes. The only
network endpoint is the explicitly selected localhost QEMU chardev.
"""

import argparse
import json
import os
import socket
import subprocess
import threading
import time
from pathlib import Path


def write_all(stream, data):
    view = memoryview(data)
    while view:
        count = stream.write(view)
        if not count:
            raise BrokenPipeError("Renderer stdin closed")
        view = view[count:]


class SocketRendererBridge:
    def __init__(self, port, renderer, renderer_args=(), dll_dir=None, log_dir=None,
                 host="127.0.0.1", capture=False, extra_env=None):
        if host != "127.0.0.1":
            raise ValueError("This prototype only connects to localhost")
        self.port, self.host = int(port), host
        self.renderer = Path(renderer).resolve()
        self.command = [str(self.renderer), *map(str, renderer_args)]
        self.dll_dir = Path(dll_dir).resolve() if dll_dir else None
        self.log_dir = (Path(log_dir).resolve() if log_dir else
                        Path(__file__).resolve().parent / f"bridge-{time.time_ns()}")
        self.capture = capture
        self.extra_env = dict(extra_env or {})
        self.process = None
        self.sock = None
        self.stop_event = threading.Event()
        self.threads = []
        self.errors = []
        self.guest_to_renderer = 0
        self.renderer_to_guest = 0
        self.started = None

    def start(self, connect_timeout=10):
        if not self.renderer.is_file():
            raise FileNotFoundError(self.renderer)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        env = os.environ.copy()
        if self.dll_dir:
            env["PATH"] = str(self.dll_dir) + os.pathsep + env.get("PATH", "")
        env.update({str(k): str(v) for k, v in self.extra_env.items()})
        self.process = subprocess.Popen(self.command, cwd=self.renderer.parent,
                                        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE, bufsize=0, env=env,
                                        creationflags=subprocess.CREATE_NO_WINDOW)
        deadline = time.monotonic() + connect_timeout
        try:
            while True:
                try:
                    self.sock = socket.create_connection((self.host, self.port), timeout=0.5)
                    break
                except OSError:
                    if self.process.poll() is not None or time.monotonic() >= deadline:
                        raise
                    time.sleep(0.05)
            self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self.sock.settimeout(None)
            self.started = time.monotonic()
            for target, name in ((self._to_renderer, "qemu-to-renderer"),
                                 (self._to_guest, "renderer-to-qemu"),
                                 (self._stderr, "renderer-stderr")):
                thread = threading.Thread(target=target, name=name, daemon=True)
                thread.start()
                self.threads.append(thread)
        except BaseException:
            self.stop()
            raise
        return self

    def _record_error(self, where, error):
        if not self.stop_event.is_set():
            self.errors.append({"where": where, "error": repr(error)})
            self.stop_event.set()

    def _to_renderer(self):
        capture = open(self.log_dir / "guest-stream.bin", "wb") if self.capture else None
        try:
            while not self.stop_event.is_set():
                chunk = self.sock.recv(65536)
                if not chunk:
                    break
                if capture:
                    capture.write(chunk)
                write_all(self.process.stdin, chunk)
                self.guest_to_renderer += len(chunk)
        except (OSError, ValueError) as error:
            self._record_error("qemu-to-renderer", error)
        finally:
            if capture:
                capture.close()
            try:
                self.process.stdin.close()
            except (OSError, ValueError):
                pass

    def _to_guest(self):
        capture = open(self.log_dir / "renderer-replies.bin", "wb") if self.capture else None
        try:
            while not self.stop_event.is_set():
                # os.read returns available pipe data; buffered read(N) could
                # wait for N bytes and deadlock a small synchronous GL reply.
                chunk = os.read(self.process.stdout.fileno(), 65536)
                if not chunk:
                    break
                if capture:
                    capture.write(chunk)
                self.sock.sendall(chunk)
                self.renderer_to_guest += len(chunk)
        except (OSError, ValueError) as error:
            self._record_error("renderer-to-qemu", error)
        finally:
            if capture:
                capture.close()

    def _stderr(self):
        try:
            with open(self.log_dir / "renderer-stderr.log", "wb") as output:
                while True:
                    chunk = os.read(self.process.stderr.fileno(), 65536)
                    if not chunk:
                        break
                    output.write(chunk)
                    output.flush()
        except (OSError, ValueError) as error:
            self._record_error("renderer-stderr", error)

    def stop(self):
        self.stop_event.set()
        if self.sock:
            try:
                self.sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            self.sock.close()
        if self.process and self.process.poll() is None:
            try:
                self.process.stdin.close()
            except (OSError, ValueError):
                pass
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.terminate()
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=5)
        for thread in self.threads:
            thread.join(timeout=2)
        result = {"kind": "BINARY_QEMU_RENDERER_RELAY_NOT_A_RENDERER",
                  "renderer": self.command, "qemu_endpoint": [self.host, self.port],
                  "guest_to_renderer_bytes": self.guest_to_renderer,
                  "renderer_to_guest_bytes": self.renderer_to_guest,
                  "elapsed_seconds": time.monotonic() - self.started if self.started else None,
                  "renderer_exit_code": self.process.returncode if self.process else None,
                  "errors": self.errors}
        if self.log_dir.exists():
            (self.log_dir / "relay-result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        return result

    def __enter__(self):
        return self.start()

    def __exit__(self, *_):
        self.stop()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu-port", type=int, required=True)
    parser.add_argument("--renderer", type=Path, required=True)
    parser.add_argument("--renderer-arg", action="append", default=[])
    parser.add_argument("--dll-dir", type=Path)
    parser.add_argument("--log-dir", type=Path)
    parser.add_argument("--seconds", type=int, default=30)
    parser.add_argument("--capture", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.seconds <= 300:
        parser.error("--seconds must be in 1..300")
    bridge = SocketRendererBridge(args.qemu_port, args.renderer, args.renderer_arg,
                                  args.dll_dir, args.log_dir, capture=args.capture)
    bridge.start()
    try:
        deadline = time.monotonic() + args.seconds
        while (time.monotonic() < deadline and not bridge.stop_event.is_set()
               and bridge.process.poll() is None):
            time.sleep(0.05)
    finally:
        print(json.dumps(bridge.stop(), indent=2))


if __name__ == "__main__":
    main()
