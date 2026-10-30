# © 2026 davisod & JEtsKi
"""Bounded original-QNX guest-library -> UART -> Windows GLES integration.

The IFS is supplied by the guest-library build. Unlike graphics_transport_probe,
this runner boots the recovered original QNX startup/kernel and waits for a
verdict produced by the compiled QNX library, loaded by QNX's dynamic linker.
This is a graphics ABI/transport probe, not an NBT HMI simulator.
"""

import argparse
import ctypes
import hashlib
import importlib.util
import json
import re
import socket
import struct
import subprocess
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True
from serial_bridge_probe import QEMU
from stdio_socket_bridge import SocketRendererBridge

HERE = Path(__file__).resolve().parent
GRAPHICS = HERE.parent
WORKSPACE = GRAPHICS.parents[1]
RESEARCH = WORKSPACE / "outputs/NBT_emulation_research"
PASS = "NBT_QNX_GRAPHICS_PROBE_PASS"
FAIL = "NBT_QNX_GRAPHICS_PROBE_FAIL"
RECOVERED_KERNEL_SHA256 = "ddd7d83d85514a8998e87618cc4eaabcf422d3a57b6279f92c6fa9c6cc2b84ca"


def load_boot_experiment():
    spec = importlib.util.spec_from_file_location("nbt_boot_experiment", RESEARCH / "boot_experiment.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def captured_file(path):
    if not path.is_file():
        return {"path": str(path), "exists": False, "bytes": 0}
    data = path.read_bytes()
    return {"path": str(path), "exists": True, "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest()}


def source_kernel_evidence(source):
    """Hash the kernel actually embedded in this uncompressed custom IFS.

    The reference digest was recorded from recovered procnto-smp-instr in
    intel_ifs_inventory.json. Checking a separate copy alone would not establish
    what the probe boots.
    """
    image = source.read_bytes()
    startup_size = struct.unpack_from("<I", image, 32)[0]
    filesystem = image[startup_size:]
    directory = struct.unpack_from("<I", filesystem, 16)[0]
    at = directory
    while at + 24 <= len(filesystem):
        size = struct.unpack_from("<H", filesystem, at)[0]
        if not size:
            break
        if size < 24 or at + size > len(filesystem):
            raise ValueError("Invalid IFS directory entry")
        mode = struct.unpack_from("<I", filesystem, at + 8)[0]
        if mode & 0o170000 == 0o100000:
            entry = filesystem[at:at + size]
            name = entry[32:].split(b"\0", 1)[0].decode()
            if name == "proc/boot/procnto-smp-instr":
                offset, length = struct.unpack_from("<II", entry, 24)
                if offset + length > len(filesystem):
                    raise ValueError("IFS kernel payload exceeds the filesystem")
                digest = hashlib.sha256(filesystem[offset:offset + length]).hexdigest()
                return {"kernel_path_in_ifs": name, "kernel_bytes": length,
                        "kernel_sha256": digest,
                        "reference_kernel_sha256": RECOVERED_KERNEL_SHA256,
                        "recovered_kernel_matches": digest == RECOVERED_KERNEL_SHA256}
        at += size
    raise ValueError("The supplied IFS has no proc/boot/procnto-smp-instr payload")


def classify_qnx_evidence(source, serial, monitor):
    evidence = source_kernel_evidence(source)
    match = re.search(r"CR0=([0-9a-fA-F]+)", monitor)
    paging = bool(match and int(match.group(1), 16) & 0x80000000)
    shell = "ORIGINAL_QNX_SHELL_RUNNING" in serial
    pidin = bool("CPU:X86 Release:6.5.0" in serial and
                 re.search(r"Processes:\s*\d+,\s*Threads:\s*\d+", serial))
    evidence.update(paging_enabled=paging, observed_cr0=match.group(1) if match else None,
                    shell_marker_seen=shell, native_pidin_report_seen=pidin,
                    qnx_serial_shell_confirmed=shell and pidin,
                    qnx_kernel_execution_confirmed=bool(shell and pidin and paging and
                                                        evidence["recovered_kernel_matches"]))
    return evidence


def run(source, seconds, transport="uart"):
    if transport not in ("uart", "virtio"):
        raise ValueError("Transport must be uart or virtio")
    source = source.resolve()
    renderer = GRAPHICS / "host/nbt-glhost.exe"
    dll_dir = GRAPHICS / "host/angle/angle-x64/bin"
    for dependency in (source, QEMU, renderer, dll_dir / "libEGL.dll", dll_dir / "libGLESv2.dll"):
        if not dependency.is_file():
            raise FileNotFoundError(dependency)
    ctypes.windll.kernel32.SetErrorMode(0x0001 | 0x0002 | 0x8000)
    boot = load_boot_experiment()
    folder = HERE / f"qnx-graphics-probe-{time.time_ns()}"
    folder.mkdir()
    envelope = folder / "original_qnx_graphics_probe.elf"
    image = boot.make_envelope(source, envelope, provide_memory=True,
                               memory_layout="nbt-map", startup_max_cpus=1,
                               qemu_clock_adapter=True)
    serial_path = folder / "serial_com1.log"
    monitor_path = folder / "monitor.log"
    stderr_path = folder / "qemu-stderr.log"
    with socket.socket() as reserve:
        reserve.bind(("127.0.0.1", 0))
        port = reserve.getsockname()[1]
    command = [str(QEMU), "-machine", "pc", "-accel", "tcg,thread=single", "-cpu", "qemu32",
               "-m", "512M", "-smp", "1", "-icount", "shift=6,sleep=off",
               "-kernel", str(envelope), "-display", "none",
               "-serial", "file:" + str(serial_path), "-monitor", "stdio", "-nic", "none",
               "-no-reboot", "-no-shutdown"]
    if transport == "uart":
        command.extend(["-chardev",
                        f"socket,id=glbridge,host=127.0.0.1,port={port},server=on,wait=on,nodelay=on",
                        "-device", "isa-serial,index=1,iobase=0x2f8,irq=3,baudbase=1000000000,chardev=glbridge"])
    else:
        command.extend(["-device", "virtio-serial-pci,id=vfast,disable-modern=on,disable-legacy=off,max_ports=1",
                        "-chardev", f"socket,id=glbridge,host=127.0.0.1,port={port},server=on,wait=on,nodelay=on",
                        "-device", "virtconsole,chardev=glbridge,bus=vfast.0,nr=0"])
    bridge = SocketRendererBridge(port, renderer, dll_dir=dll_dir, log_dir=folder / "relay",
                                  capture=True,
                                  extra_env={"MHI2_SHADER_CACHE": GRAPHICS / "host/shader-cache",
                                             "MHI2_GL_FRAME": folder / "frame.ppm"})
    result = {"test": "ORIGINAL_QNX_GUEST_LIBRARY_WINDOWS_GLES_INTEGRATION",
              "transport": transport,
              "not_an_nbt_hmi_run": True, "source_ifs": str(source), "image": image,
              "qemu_command": command, "run_directory": str(folder),
              "probe_timeout_seconds": seconds, "success": False}
    process = None
    started = time.monotonic()
    with open(monitor_path, "wb") as monitor, open(stderr_path, "wb") as stderr:
        try:
            process = subprocess.Popen(command, cwd=QEMU.parent, stdin=subprocess.PIPE,
                                       stdout=monitor, stderr=stderr,
                                       creationflags=subprocess.CREATE_NO_WINDOW)
            bridge.start(connect_timeout=min(10, seconds))
            deadline = started + seconds
            while True:
                serial = serial_path.read_text(errors="replace") if serial_path.exists() else ""
                if FAIL in serial:
                    raise RuntimeError("The compiled QNX guest probe reported FAIL")
                if PASS in serial:
                    result["guest_pass_verdict_seen"] = True
                    break
                if "ldd:FATAL:" in serial:
                    raise RuntimeError("The QNX dynamic loader reported a fatal error before the probe verdict")
                if "GRAPHICS_PROBE_FINISHED" in serial:
                    raise RuntimeError("The QNX probe process finished without its PASS verdict")
                if process.poll() is not None:
                    raise RuntimeError("QEMU exited before the QNX guest verdict")
                if bridge.process.poll() is not None:
                    raise RuntimeError("The Windows renderer exited before the QNX guest verdict")
                if bridge.errors:
                    raise RuntimeError(f"The binary relay reported errors: {bridge.errors}")
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"No QNX graphics verdict within {seconds} seconds")
                time.sleep(0.05)
        except BaseException as error:
            result["error"] = repr(error)
        finally:
            result["elapsed_until_verdict_or_failure"] = time.monotonic() - started
            # The verdict follows synchronous replies. Close the now-idle
            # relay before quitting QEMU so expected TCP teardown is not
            # misreported as a renderer/transport failure.
            result["relay"] = bridge.stop()
            if process and process.poll() is None:
                try:
                    process.stdin.write(b"info registers\ninfo cpus\ninfo lapic\ninfo irq\nquit\n")
                    process.stdin.flush()
                    process.wait(timeout=3)
                except (OSError, ValueError, subprocess.TimeoutExpired):
                    process.terminate()
                    try:
                        process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=3)
            if process and process.stdin:
                process.stdin.close()
            result["qemu_exit_code"] = process.returncode if process else None
    serial = serial_path.read_text(errors="replace") if serial_path.exists() else ""
    monitor = monitor_path.read_text(errors="replace")
    result["legacy_boot_classifier"] = boot.classify_evidence({"1": serial}, monitor)
    result["qnx_evidence"] = classify_qnx_evidence(source, serial, monitor)
    result["guest_pass_verdict_seen"] = PASS in serial
    result["guest_fail_verdict_seen"] = FAIL in serial
    result["serial"] = serial
    result["qemu_stderr"] = stderr_path.read_text(errors="replace")
    result["captures"] = {"guest_commands": captured_file(folder / "relay/guest-stream.bin"),
                          "renderer_replies": captured_file(folder / "relay/renderer-replies.bin"),
                          "frame": captured_file(folder / "frame.ppm")}
    result["success"] = bool(result["guest_pass_verdict_seen"] and not result["guest_fail_verdict_seen"]
                             and result["qnx_evidence"]["qnx_serial_shell_confirmed"]
                             and result["qnx_evidence"]["qnx_kernel_execution_confirmed"]
                             and result["relay"]["guest_to_renderer_bytes"] > 0
                             and result["relay"]["renderer_to_guest_bytes"] > 0
                             and result["relay"]["renderer_exit_code"] == 0
                             and not result["relay"]["errors"] and "error" not in result)
    result["elapsed_total_seconds"] = time.monotonic() - started
    (folder / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ifs", type=Path, default=GRAPHICS / "guest/graphics_probe.ifs")
    parser.add_argument("--seconds", type=int, choices=range(1, 31), default=30)
    parser.add_argument("--transport", choices=("uart", "virtio"), default="uart",
                        help="Must match the transport compiled into the supplied QNX IFS")
    args = parser.parse_args()
    result = run(args.ifs, args.seconds, args.transport)
    print(json.dumps(result, indent=2), flush=True)
    if not result["success"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
