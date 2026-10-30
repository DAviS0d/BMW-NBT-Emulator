"""© 2026 davisod & JEtsKi
Bridge v2 build script: builds guest libnbtgl.so (QNX i386) and host nbt-glhost-v2.exe (Windows x64) with zig cc.

Usage:  py -3 build.py [guest|host|tests|all]   (default: all = guest + host)
"""
import hashlib
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(ROOT, "..", ".."))
ZIG = os.path.join(REPO, "work", "graphics-port", "toolchain", "zig-x86_64-windows-0.15.2", "zig.exe")
ANGLE = os.path.join(REPO, "work", "graphics-port", "host", "angle", "angle-x64")

GUEST_SOURCES = ["rt.c", "virtio.c", "dma.c", "link.c", "gles.c", "egl.c", "stubs.c", "input.c", "keyboard.c"]
HOST_SOURCES = ["main.c", "logx.c", "channel.c", "dmaring.c", "idle.c", "validate.c", "render.c", "publish.c", "shaders.c"]

GUEST_FLAGS = [
    "-target", "x86-linux-gnu", "-mcpu=pentium4", "-mstackrealign",
    "-ffreestanding", "-fno-builtin", "-fno-stack-protector", "-nostdlib", "-fPIC", "-O2", "-shared",
    "-fvisibility=hidden", "-fno-asynchronous-unwind-tables", "-fno-unwind-tables",
    "-Wall", "-Wextra", "-Wno-unused-parameter",
    "-Wl,--hash-style=sysv", "-Wl,-z,norelro", "-Wl,-soname,libnbtgl.so",
]

HOST_FLAGS = [
    "-target", "x86_64-windows-gnu", "-O2", "-std=c11", "-Wall", "-Wextra", "-Wno-unused-parameter",
    "-DWIN32_LEAN_AND_MEAN",
]


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def run(cmd):
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True)


def build_guest():
    gdir = os.path.join(ROOT, "guest")
    out = os.path.join(gdir, "libnbtgl.so")
    run([ZIG, "cc", *GUEST_FLAGS, "-o", out, *[os.path.join(gdir, s) for s in GUEST_SOURCES]])
    print(f"guest  {out}\n  sha256 {sha256(out)}", flush=True)
    return out


def build_native_guest():
    """Build the isolated, opt-in original-HMI extension profile."""
    gdir = os.path.join(ROOT, 'guest')
    out = os.path.join(gdir, 'libnbtgl-native.so')
    sources = GUEST_SOURCES + ['native_patch.c', 'native_sports.c', 'native_devices.c']
    run([ZIG, 'cc', *GUEST_FLAGS, '-DNBT_EXPERIMENTAL_NATIVE=1', '-o', out,
         *[os.path.join(gdir, name) for name in sources]])
    print(f'native guest {out}\n  sha256 {sha256(out)}', flush=True)
    return out


def host_link_inputs():
    lib = os.path.join(ANGLE, "lib")
    return [
        "-I", os.path.join(ANGLE, "include"),
        os.path.join(lib, "libEGL.dll.lib"), os.path.join(lib, "libGLESv2.dll.lib"),
        "-lws2_32", "-lkernel32", "-luser32",
    ]


def build_host():
    hdir = os.path.join(ROOT, "host")
    out = os.path.join(hdir, "nbt-glhost-v2.exe")
    run([ZIG, "cc", *HOST_FLAGS, "-o", out, *[os.path.join(hdir, s) for s in HOST_SOURCES], *host_link_inputs()])
    for junk in ("nbt-glhost-v2.pdb", "nbt-glhost-v2.lib"):
        p = os.path.join(hdir, junk)
        if os.path.exists(p):
            os.remove(p)
    print(f"host   {out}\n  sha256 {sha256(out)}", flush=True)
    return out


def build_tests():
    """Ring/validator harness: host modules without GL, linked with the test driver."""
    hdir = os.path.join(ROOT, "host")
    tdir = os.path.join(ROOT, "tests")
    out = os.path.join(tdir, "ring_harness.exe")
    srcs = [os.path.join(tdir, "ring_harness.c")] + [os.path.join(hdir, s) for s in ("logx.c", "dmaring.c", "idle.c", "validate.c", "shaders.c")]
    run([ZIG, "cc", *HOST_FLAGS, "-I", hdir, "-I", os.path.join(ANGLE, "include"), "-o", out, *srcs, "-lkernel32"])
    for junk in ("ring_harness.pdb", "ring_harness.lib"):
        p = os.path.join(tdir, junk)
        if os.path.exists(p):
            os.remove(p)
    print(f"tests  {out}\n  sha256 {sha256(out)}", flush=True)
    return out


def main():
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    if what == 'native-guest':
        build_native_guest()
        return
    if what in ("guest", "all"):
        build_guest()
    if what in ("host", "all"):
        build_host()
    if what == "tests":
        build_tests()


if __name__ == "__main__":
    main()
