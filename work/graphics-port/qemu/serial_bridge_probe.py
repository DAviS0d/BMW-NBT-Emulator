# © 2026 davisod & JEtsKi
"""Verify binary full-duplex COM2 transport through the existing Windows QEMU.

This creates a tiny bare-metal Multiboot x86 payload which configures COM2,
announces readiness, receives N bytes, XORs them with 0xa5 and sends them back.
No QNX or NVIDIA code is involved; this tests only the proposed GL transport.
"""

import argparse
import concurrent.futures
import hashlib
import json
import socket
import struct
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WORKSPACE = ROOT.parents[2]
QEMU = WORKSPACE / "work/emulation-tools/qemu-portable/qemu-system-i386.exe"


class Code:
    def __init__(self, base=0x100000):
        self.base = base
        self.data = bytearray()
        self.labels = {}
        self.fixups = []

    def emit(self, data):
        self.data.extend(data)

    def label(self, name):
        self.labels[name] = len(self.data)

    def rel(self, prefix, target):
        self.emit(prefix)
        self.fixups.append((len(self.data), target, False))
        self.emit(b"\0" * 4)

    def absolute(self, prefix, target):
        self.emit(prefix)
        self.fixups.append((len(self.data), target, True))
        self.emit(b"\0" * 4)

    def finish(self):
        for at, target, absolute in self.fixups:
            value = self.base + self.labels[target] if absolute else self.labels[target] - (at + 4)
            struct.pack_into("<I", self.data, at, value & 0xFFFFFFFF)
        return bytes(self.data)


def make_payload(count):
    c = Code()
    c.emit(b"\xfa\xfc\xbc" + struct.pack("<I", 0x90000))
    # Disable interrupts; divisor=1, 8N1; enable/clear FIFO; assert DTR/RTS.
    for port, value in ((0x2F9, 0), (0x2FB, 0x80), (0x2F8, 1), (0x2F9, 0),
                        (0x2FB, 3), (0x2FA, 7), (0x2FC, 3)):
        c.emit(b"\x66\xba" + struct.pack("<H", port) + b"\xb0" + bytes([value]) + b"\xee")
    c.absolute(b"\xbe", "greeting")
    c.rel(b"\xe8", "send_string")
    c.emit(b"\xb9" + struct.pack("<I", count))
    c.label("echo_loop")
    c.rel(b"\xe8", "receive_char")
    c.emit(b"\x34\xa5")
    c.rel(b"\xe8", "send_char")
    c.emit(b"\x49")
    c.rel(b"\x0f\x85", "echo_loop")
    c.absolute(b"\xbe", "done")
    c.rel(b"\xe8", "send_string")
    c.label("halt")
    c.emit(b"\xf4")
    c.rel(b"\xe9", "halt")
    c.label("send_string")
    c.emit(b"\xac\x84\xc0")
    c.rel(b"\x0f\x84", "string_done")
    c.rel(b"\xe8", "send_char")
    c.rel(b"\xe9", "send_string")
    c.label("string_done")
    c.emit(b"\xc3")
    c.label("send_char")
    c.emit(b"\x50")  # preserve the character while polling LSR
    c.label("send_wait")
    c.emit(b"\x66\xba\xfd\x02\xec\xa8\x20")
    c.rel(b"\x0f\x84", "send_wait")
    c.emit(b"\x58\x66\xba\xf8\x02\xee\xc3")
    c.label("receive_char")
    c.emit(b"\x66\xba\xfd\x02\xec\xa8\x01")
    c.rel(b"\x0f\x84", "receive_char")
    c.emit(b"\x66\xba\xf8\x02\xec\xc3")
    c.label("greeting")
    c.emit(b"NBT UART TRANSPORT READY\n\0")
    c.label("done")
    c.emit(b"OK\n\0")
    payload = c.finish()
    elf = bytearray(0x1000 + len(payload))
    ident = b"\x7fELF\x01\x01\x01" + b"\0" * 9
    struct.pack_into("<16sHHIIIIIHHHHHH", elf, 0, ident, 2, 3, 1, c.base,
                     52, 0, 0, 52, 32, 1, 40, 0, 0)
    struct.pack_into("<8I", elf, 52, 1, 0x1000, c.base, c.base,
                     len(payload), 0x1000, 5, 0x1000)
    magic, flags = 0x1BADB002, 3
    struct.pack_into("<3I", elf, 0x100, magic, flags, -(magic + flags) & 0xFFFFFFFF)
    elf[0x1000:] = payload
    return bytes(elf)


def recv_exact(sock, size):
    chunks = bytearray()
    while len(chunks) < size:
        chunk = sock.recv(size - len(chunks))
        if not chunk:
            raise EOFError(f"Socket closed at {len(chunks)}/{size} bytes")
        chunks.extend(chunk)
    return bytes(chunks)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bytes", type=int, default=65536)
    parser.add_argument("--baudbase", type=int, default=1_000_000_000)
    args = parser.parse_args()
    if not 1 <= args.bytes <= 4 * 1024 * 1024:
        parser.error("--bytes must be 1..4194304")
    if not QEMU.is_file():
        raise FileNotFoundError(QEMU)
    with socket.socket() as reserve:
        reserve.bind(("127.0.0.1", 0))
        port = reserve.getsockname()[1]
    folder = ROOT / f"probe-{time.time_ns()}"
    folder.mkdir()
    elf = folder / "uart_probe.elf"
    elf.write_bytes(make_payload(args.bytes))
    command = [str(QEMU), "-machine", "pc", "-accel", "tcg,thread=single",
               "-cpu", "qemu32", "-m", "32M", "-nodefaults", "-display", "none",
               "-nic", "none", "-monitor", "none", "-kernel", str(elf),
               "-no-reboot", "-no-shutdown", "-chardev",
               f"socket,id=glbridge,host=127.0.0.1,port={port},server=on,wait=on,nodelay=on",
               "-device", f"isa-serial,index=1,iobase=0x2f8,irq=3,baudbase={args.baudbase},chardev=glbridge"]
    process = subprocess.Popen(command, cwd=QEMU.parent, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, creationflags=subprocess.CREATE_NO_WINDOW)
    result = {"kind": "REAL_STOCK_QEMU_UART_TRANSPORT_PROBE_NOT_GRAPHICS", "command": command}
    try:
        deadline = time.monotonic() + 10
        while True:
            try:
                sock = socket.create_connection(("127.0.0.1", port), timeout=0.5)
                break
            except OSError:
                if process.poll() is not None or time.monotonic() >= deadline:
                    raise
                time.sleep(0.05)
        with sock:
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            sock.settimeout(60)
            greeting = recv_exact(sock, len(b"NBT UART TRANSPORT READY\n"))
            assert greeting == b"NBT UART TRANSPORT READY\n", greeting
            data = (bytes(range(256)) * ((args.bytes + 255) // 256))[:args.bytes]
            expected = bytes(x ^ 0xA5 for x in data)
            started = time.perf_counter()
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                writer = executor.submit(sock.sendall, data)
                received = recv_exact(sock, len(data))
                writer.result(timeout=10)
            done = recv_exact(sock, 3)
            elapsed = time.perf_counter() - started
            assert received == expected
            assert done == b"OK\n", done
            result.update(success=True, bytes_each_direction=len(data), elapsed_seconds=elapsed,
                          full_duplex_payload_bytes_per_second=2 * len(data) / elapsed,
                          returned_sha256=hashlib.sha256(received).hexdigest())
    except BaseException as error:
        result.update(success=False, error=repr(error))
    finally:
        process.terminate()
        try:
            stdout, stderr = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate()
        result["qemu_stderr"] = stderr.decode(errors="replace")
        (folder / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    if not result.get("success"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
