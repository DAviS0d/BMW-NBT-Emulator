"""© 2026 davisod & JEtsKi
Bridge v2 self-test: drives nbt-glhost-v2.exe with real ANGLE in stdio mode and socket mode (no VM).

Covers: window/initial frame, client selection, getters with byte-exact reply sizes, EBO max-index query (op 138
on indices [2, 7, 1] -> 7), glReadPixels reply, PPM publication (flip, size), invalid record, video record exit 3,
op 144 without DMA config (ack 0, no "client disconnected"), socket mode control EOF semantics.
"""
import os
import socket
import struct
import subprocess
import sys
import tempfile
import threading

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.abspath(os.path.join(ROOT, "..", ".."))
EXE = os.path.join(ROOT, "host", "nbt-glhost-v2.exe")
ANGLE_BIN = os.path.join(REPO, "work", "graphics-port", "host", "angle", "angle-x64", "bin")

FAILS = []


def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg, flush=True)
    if not cond:
        FAILS.append(msg)


def rec(op, *fields, raw=b""):
    body = b"".join(struct.pack("<I", f & 0xFFFFFFFF) if isinstance(f, int) else struct.pack("<f", f) for f in fields) + raw
    return struct.pack("<II", op, len(body)) + body


def call(op, *fields, raw=b"", pid=4242):
    return rec(119, pid) + rec(op, *fields, raw=raw)


def env_for(workdir, **extra):
    env = dict(os.environ)
    env["PATH"] = ANGLE_BIN + os.pathsep + env.get("PATH", "")
    env["MHI2_GL_FRAME"] = os.path.join(workdir, "frame.ppm")
    for k in ("GLHOST_QEMU_PORT", "GLHOST_DMA_CONFIG", "MHI2_GL_TRACE", "MHI2_GL_DUMP_CLIENTS", "MHI2_GL_CAPTURE"):
        env.pop(k, None)
    env.update(extra)
    return env


def run_stdio(stream, workdir, **extra):
    p = subprocess.run([EXE], input=stream, capture_output=True, cwd=workdir, env=env_for(workdir, **extra), timeout=120)
    return p.returncode, p.stdout, p.stderr.decode(errors="replace")


def read_ppm(path):
    data = open(path, "rb").read()
    parts = data.split(b"\n", 3)
    w, h = map(int, parts[1].split())
    return w, h, parts[3], len(data)


def test_stdio_session(workdir):
    W, H = 64, 32
    s = b""
    s += call(1, W, H)
    s += call(2, 0, 0, W, H)
    s += call(3, 1.0, 0.0, 0.0, 1.0)
    s += call(4, 0x4000)
    s += call(105)                                   # reply 4: GL_NO_ERROR
    s += call(104, 0x0BA2)                           # reply 64: viewport
    s += call(15, 1, 5)                              # gen buffer name 5
    s += call(16, 0x8893, 5)
    s += call(17, 0x8893, 6, 0x88E4, raw=struct.pack("<HHH", 2, 7, 1))
    s += call(138, 3, 0x1403, 0)                     # reply 4: max index 7
    s += call(16, 0x8893, 0)
    s += call(138, 3, 0x1403, 0)                     # no EBO: 0xFFFFFFFF
    s += call(105)                                   # INVALID_OPERATION from the hidden size query
    s += call(105)                                   # cleared
    s += call(120, 0, 0, 2, 2, 0x1908, 0x1401)       # reply 16
    s += call(104, 0x86A2)                           # excluded pname: zeros, no GL call
    s += call(142, 0x0BE2)                           # glIsEnabled(BLEND) -> 0
    s += call(5)
    rc, out, err = run_stdio(s, workdir)
    expect = 4 + 64 + 4 + 4 + 4 + 4 + 16 + 64 + 4
    check(rc == 0, f"stdio session exit 0 (rc={rc})")
    check(len(out) == expect, f"reply byte count {len(out)} == {expect}")
    if len(out) == expect:
        o = 0
        e1, = struct.unpack_from("<I", out, o); o += 4
        vp = struct.unpack_from("<16i", out, o); o += 64
        mx, = struct.unpack_from("<I", out, o); o += 4
        mx2, = struct.unpack_from("<I", out, o); o += 4
        e2, = struct.unpack_from("<I", out, o); o += 4
        e3, = struct.unpack_from("<I", out, o); o += 4
        px = out[o:o + 16]; o += 16
        ex = out[o:o + 64]; o += 64
        en, = struct.unpack_from("<I", out, o)
        check(e1 == 0, "glGetError after clear == 0")
        check(vp[:4] == (0, 0, W, H) and all(v == 0 for v in vp[4:]), f"GL_VIEWPORT reply {vp[:4]}")
        check(mx == 7, f"op 138 max index of [2,7,1] == 7 (got {mx})")
        check(mx2 == 0xFFFFFFFF, "op 138 without EBO == 0xFFFFFFFF")
        check(e2 == 0x0502, f"hidden glGetBufferParameteriv error surfaces (0x{e2:x})")
        check(e3 == 0, "error flag cleared")
        check(px == bytes([255, 0, 0, 255]) * 4, "glReadPixels returns red RGBA")
        check(ex == b"\0" * 64, "excluded pname -> zeros")
        check(en == 0, "glIsEnabled(BLEND) == 0")
    check("glhost: window 64x32, GLES = " in err, "window log line")
    check("glhost: 1 frames swapped" in err, "frames swapped line")
    check("glhost: client disconnected after 1 frames" in err, "disconnect line after EOF")
    w, h, pix, size = read_ppm(os.path.join(workdir, "frame.ppm"))
    check((w, h) == (W, H) and size == len(f"P6\n{W} {H}\n255\n") + W * H * 3, f"PPM {w}x{h} size {size}")
    check(pix[:3] == b"\xff\x00\x00" and pix[-3:] == b"\xff\x00\x00", "PPM content is the red frame")
    check(not os.path.exists(os.path.join(workdir, "frame.ppm.tmp")), "no leftover .tmp")


def test_flip(workdir):
    W, H = 16, 8
    s = call(1, W, H)
    s += call(33, 0x0C11)                            # GL_SCISSOR_TEST
    s += call(3, 0.0, 0.0, 1.0, 1.0) + call(65, 0, 0, W, H) + call(4, 0x4000)
    s += call(3, 0.0, 1.0, 0.0, 1.0) + call(65, 0, H - 1, W, 1) + call(4, 0x4000)   # top GL row green
    s += call(5)
    rc, out, err = run_stdio(s, workdir)
    w, h, pix, _ = read_ppm(os.path.join(workdir, "frame.ppm"))
    check(rc == 0 and pix[:3] == b"\x00\xff\x00" and pix[-3:] == b"\x00\x00\xff", "PPM rows are flipped (top = last GL row)")


def test_invalid(workdir):
    rc, out, err = run_stdio(call(1, 32, 32) + rec(41), workdir)
    check(rc == 0 and "Invalid graphics record: op=41 len=0" in err and "client disconnected after 0 frames" in err,
          "invalid record ends session with exit 0")


def test_video(workdir):
    rc, out, err = run_stdio(call(1, 32, 32) + call(122, 0), workdir)
    check(rc == 3 and "Unsupported video/encoder record 122" in err, f"video record -> exit 3 (rc={rc})")


def test_144_without_config(workdir):
    payload = struct.pack("<IIIIIII", 0x100000, 135168, 2, 42, 73, 101, 0x100000)
    rc, out, err = run_stdio(rec(144, raw=payload), workdir)
    check(rc == 0 and out == b"\0\0\0\0" and "client disconnected" not in err, "op 144 without config: ack 0, silent end")


def test_socket(workdir):
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]
    p = subprocess.Popen([EXE], stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                         cwd=workdir, env=env_for(workdir, GLHOST_QEMU_PORT=str(port)))
    conn, _ = srv.accept()
    lines = []

    def pump():
        for line in p.stderr:
            lines.append(line.decode(errors="replace").rstrip("\r\n"))
    t = threading.Thread(target=pump, daemon=True)
    t.start()
    conn.sendall(call(1, 48, 24) + call(105) + call(5))
    got = b""
    while len(got) < 4:
        chunk = conn.recv(4 - len(got))
        if not chunk:
            break
        got += chunk
    check(got == b"\0\0\0\0", "socket mode reply via socket")
    p.stdin.close()                                   # control EOF
    rc = p.wait(timeout=30)
    t.join(timeout=5)
    conn.close()
    srv.close()
    text = "\n".join(lines)
    check(f"GLHOST_NATIVE_SOCKET_CONNECTED port={port}" in text, "CONNECTED marker")
    check(rc == 0, f"socket mode exit 0 (rc={rc})")
    check("glhost: client disconnected after 1 frames" in text, "socket: disconnect line")
    check("GLHOST_NATIVE_SOCKET_STOP control_eof=1 control_joined=1" in text, "control_eof=1 control_joined=1")
    counts = [l for l in lines if l.startswith("GLHOST_NATIVE_SOCKET_COUNTS")]
    check(counts == ["GLHOST_NATIVE_SOCKET_COUNTS rx=%d tx=4" % len(call(1, 48, 24) + call(105) + call(5))],
          f"socket counts {counts}")
    order = [i for i, l in enumerate(lines) if l.startswith(("glhost: client disconnected", "GLHOST_NATIVE_SOCKET_COUNTS", "GLHOST_NATIVE_SOCKET_STOP"))]
    check(order == sorted(order) and len(order) == 3, "termination line order")


def test_socket_bad_port(workdir):
    p = subprocess.run([EXE], input=b"", capture_output=True, cwd=workdir, env=env_for(workdir, GLHOST_QEMU_PORT="70000"))
    check(p.returncode == 2 and b"GLHOST_SOCKET_ERROR invalid GLHOST_QEMU_PORT" in p.stderr, "invalid port -> exit 2")


def main():
    if not os.path.exists(EXE):
        print("missing", EXE)
        return 2
    with tempfile.TemporaryDirectory(prefix="bridge-v2-e2e-") as d:
        test_stdio_session(d)
        test_flip(d)
        test_invalid(d)
        test_video(d)
        test_144_without_config(d)
        test_socket(d)
        test_socket_bad_port(d)
    print("HOST_E2E_PASS" if not FAILS else f"HOST_E2E_FAIL ({len(FAILS)})")
    return 0 if not FAILS else 1


if __name__ == "__main__":
    sys.exit(main())
