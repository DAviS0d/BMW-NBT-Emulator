# © 2026 davisod & JEtsKi
"""Collect a bounded original-NBT HMI run without inventing a graphics verdict.

The collector records a crash, an exit, or the state at the observation limit.
Neither a collected diagnostic nor an arbitrary presented frame proves a menu.
"""
import argparse
import ctypes
import hashlib
import json
import re
import socket
import struct
import subprocess
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
GRAPHICS = HERE.parent
WORKSPACE = GRAPHICS.parents[1]
sys.path.insert(0, str(GRAPHICS / "qemu"))
from qnx_graphics_probe import QEMU, load_boot_experiment, classify_qnx_evidence
from stdio_socket_bridge import SocketRendererBridge
from native_socket_bridge import NativeSocketRendererBridge


def virtual_apic_frequency(accelerator):
    if accelerator == 'tcg':
        return 1_000_000_000
    platform = ctypes.WinDLL('WinHvPlatform.dll')
    capability = platform.WHvGetCapability
    capability.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32,
                           ctypes.POINTER(ctypes.c_uint32)]
    capability.restype = ctypes.c_long
    frequency, written = ctypes.c_uint64(), ctypes.c_uint32()
    status = capability(0x1005, ctypes.byref(frequency), ctypes.sizeof(frequency),
                        ctypes.byref(written))
    if status or written.value != ctypes.sizeof(frequency):
        raise RuntimeError(f'Cannot read WHPX interrupt clock: HRESULT0x{status & 0xffffffff:08x}')
    return frequency.value


class QmpMonitor:
    """Structured local QEMU control; avoids HMP readline input races."""
    def __init__(self, port, log_path, timeout=2):
        self.socket = socket.create_connection(("127.0.0.1", port), timeout=timeout)
        self.socket.settimeout(timeout)
        self.reader = self.socket.makefile("rb")
        self.log = Path(log_path).open("w", encoding="utf-8")
        self.serial = 0
        greeting = self._receive()
        if "QMP" not in greeting:
            raise RuntimeError("Unexpected QEMU monitor greeting")
        self.command("qmp_capabilities")

    def _record(self, direction, message):
        self.log.write(json.dumps({"direction": direction, "message": message}) + "\n")
        self.log.flush()

    def _receive(self):
        line = self.reader.readline()
        if not line:
            raise EOFError("QEMU monitor closed")
        message = json.loads(line)
        self._record("receive", message)
        return message

    def command(self, name, arguments=None):
        self.serial += 1
        request = {"execute": name, "id": self.serial}
        if arguments is not None:
            request["arguments"] = arguments
        self._record("send", request)
        self.socket.sendall((json.dumps(request) + "\n").encode("utf-8"))
        while True:
            response = self._receive()
            if response.get("id") != self.serial:
                continue  # STOP/RESUME/SHUTDOWN events may precede the reply.
            if "error" in response:
                raise RuntimeError(f"QMP {name}: {response['error']}")
            return response.get("return")

    def close(self):
        self.reader.close()
        self.socket.close()
        self.log.close()


def read_text(path):
    return path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""


def fingerprint(path):
    if not path.is_file():
        return {"path": str(path), "exists": False, "bytes": 0}
    with path.open("rb") as source:
        digest = hashlib.file_digest(source, "sha256").hexdigest()
    return {"path": str(path), "exists": True, "bytes": path.stat().st_size,
            "sha256": digest}


def classify_hmi(serial, observation_limit_reached=False):
    exits = re.findall(r"HMI_RUN_EXIT\s*=\s*(-?\d+)", serial)
    exit_code = int(exits[-1]) if exits else None
    # Match an HMI process's report, not an unrelated guest process crash.
    crash = re.search(r"Process\s+\d+\s+\(HmiMain3D\)\s+terminated\s+"
                      r"(SIG\w+)[^\r\n]*?(?:ip=([0-9a-fA-F]+))?", serial)
    crash_ip = None
    if crash:
        tail = serial[crash.start():crash.start() + 550]
        address = re.search(r"\bip=([0-9a-fA-F]+)", tail)
        crash_ip = "0x" + address.group(1).lower().zfill(8) if address else None
    callback = "NBT_HMI_CALLBACK_ADAPTER: entering original kdMain" in serial
    observed = bool(callback or crash or exit_code is not None or
                    re.search(r"\b\d+\s+\S*HmiMain3D\b", serial))
    if crash:
        state = "crashed"
    elif exit_code is not None:
        state = "exited"
    elif observed and observation_limit_reached:
        state = "active_at_observation_limit"
    elif observed:
        state = "observed_without_final_exit"
    else:
        state = "not_observed"
    return {"state": state, "launch_attempted": "HMI_ORIGINAL_RUN_TEST" in serial,
            "callback_entered": callback, "process_observed": observed,
            "exit_code": exit_code, "crash_signal": crash.group(1) if crash else None,
            "crash_ip": crash_ip,
            "loader_fatal": "ldd:FATAL:" in serial,
            "menu_verified": False}


def command_statistics(path):
    """Count only complete upstream command records, without loading textures."""
    if not path.is_file():
        return {"complete_records": 0, "swap_commands": 0, "opcodes": {},
                "trailing_bytes": 0}
    total = path.stat().st_size
    counts = {}
    used = 0
    invalid_length = None
    with path.open("rb") as stream:
        while used + 8 <= total:
            opcode, size = struct.unpack("<II", stream.read(8))
            if size > 16 * 1024 * 1024:
                invalid_length = size
                break
            if used + 8 + size > total:
                break
            counts[str(opcode)] = counts.get(str(opcode), 0) + 1
            stream.seek(size, 1)
            used += 8 + size
    return {"complete_records": sum(counts.values()),
            "swap_commands": counts.get("5", 0), "opcodes": counts,
            "trailing_bytes": total - used, "invalid_payload_length": invalid_length}


def frame_details(ppm):
    details = fingerprint(ppm)
    if not details["exists"]:
        return details
    # A PPM is evidence of actual renderer bytes, not evidence of their meaning.
    with ppm.open("rb") as source:
        header = source.read(128)
    match = re.match(rb"P6\s+(\d+)\s+(\d+)\s+255[ \t]*\r?\n", header)
    if match:
        width, height = map(int, match.groups())
        details.update(width=width, height=height,
                       complete_rgb_payload=details["bytes"] == match.end() + width * height * 3)
    else:
        details["complete_rgb_payload"] = False
    return details


def run(source, seconds=30, transport="virtio", input_port=None, synchronize_clock=False,
        instruction_counting=True, stop_event=None, on_ready=None, capture_protocol=True,
        retain_boot_image=True, idle_sleep=False, virtio_port=0, input_virtio=False, icount_shift=6,
        keyboard_hal=False, accelerator="tcg", direct_renderer=False, block_publication=False,
        dma_transport=False, renderer_path=None):
    if transport not in ("virtio", "uart") or not 1 <= seconds <= 43200:
        raise ValueError("Require seconds 1..43200 and transport virtio|uart")
    if input_port is not None and (transport != 'virtio' or not 0 <= input_port <= 65535):
        raise ValueError('COM2 input requires virtio graphics and a localhost port 0..65535')
    if virtio_port not in (0, 1) or (virtio_port and transport != 'virtio'):
        raise ValueError('Graphics virtio_port must be 0 or 1 and requires virtio transport')
    if input_virtio and (virtio_port != 1 or input_port is None):
        raise ValueError('Virtio input requires graphics port1 and an input port')
    if not 0 <= icount_shift <= 10:
        raise ValueError('Require icount shift 0..10')
    if accelerator not in ('tcg', 'whpx'):
        raise ValueError('Require accelerator tcg|whpx')
    if accelerator == 'whpx' and instruction_counting:
        raise ValueError('WHPX requires instruction_counting=False')
    if direct_renderer and capture_protocol:
        raise ValueError('Native renderer requires capture_protocol=False')
    if block_publication and not direct_renderer:
        raise ValueError('Block publication requires the native socket renderer')
    if dma_transport and (not direct_renderer or not block_publication):
        raise ValueError('DMA transport requires the native renderer and block publication')
    source = Path(source).resolve()
    qemu_program = QEMU.with_name('qemu-system-x86_64.exe') if accelerator == 'whpx' else QEMU
    renderer = GRAPHICS / ('host/nbt-glhost-socket.exe' if direct_renderer else 'host/nbt-glhost.exe')
    if block_publication:
        renderer = GRAPHICS / 'host/nbt-glhost-publish.exe'
    if dma_transport:
        renderer = GRAPHICS / 'host/nbt-glhost-dma.exe'
    if renderer_path is not None:
        renderer = Path(renderer_path).resolve()
    dll_dir = GRAPHICS / "host/angle/angle-x64/bin"
    for dependency in (source, qemu_program, renderer, dll_dir / "libEGL.dll", dll_dir / "libGLESv2.dll"):
        if not dependency.is_file():
            raise FileNotFoundError(dependency)
    ctypes.windll.kernel32.SetErrorMode(0x0001 | 0x0002 | 0x8000)
    folder = HERE / "runs" / f"run-{time.time_ns()}"
    folder.mkdir(parents=True)
    envelope = folder / "original_qnx_hmi.elf"
    boot = load_boot_experiment()
    apic_hz = virtual_apic_frequency(accelerator)
    image = boot.make_envelope(source, envelope, provide_memory=True,
                               memory_layout="nbt-map", startup_max_cpus=1,
                               qemu_clock_adapter=True, qemu_apic_hz=apic_hz)
    serial_path = folder / "serial_com1.log"
    monitor_path = folder / "monitor.log"
    stderr_path = folder / "qemu-stderr.log"
    with socket.socket() as reserve:
        reserve.bind(("127.0.0.1", 0))
        port = reserve.getsockname()[1]
    with socket.socket() as reserve:
        reserve.bind(("127.0.0.1", 0))
        monitor_port = reserve.getsockname()[1]
    accel_options = 'whpx,kernel-irqchip=on' if accelerator == 'whpx' else 'tcg,thread=single'
    command = [str(qemu_program), "-machine", "pc", "-accel", accel_options, "-cpu", "qemu32",
               "-m", "512M", "-smp", "1", "-icount",
               (f"shift={icount_shift},align=on,sleep=on" if synchronize_clock else
                f"shift={icount_shift},sleep=on" if idle_sleep else f"shift={icount_shift},sleep=off"),
               "-kernel", str(envelope), "-display", "none",
               "-serial", "file:" + str(serial_path), "-monitor", "none",
               "-qmp", f"tcp:127.0.0.1:{monitor_port},server=on,wait=off", "-nic", "none",
               "-no-reboot", "-no-shutdown"]
    if not instruction_counting:
        at = command.index('-icount')
        del command[at:at+2]
    chardev = f"socket,id=glbridge,host=127.0.0.1,port={port},server=on,wait=on,nodelay=on"
    if transport == "virtio":
        command.extend(["-device", f"virtio-serial-pci,id=vfast,disable-modern=on,disable-legacy=off,max_ports={3 if input_virtio else 2 if virtio_port else 1}",
                        "-chardev", chardev, "-device",
                        "virtserialport,chardev=glbridge,bus=vfast.0,nr=1,name=nbtgl" if virtio_port else
                        "virtconsole,chardev=glbridge,bus=vfast.0,nr=0"])
    else:
        command.extend(["-chardev", chardev, "-device",
                        "isa-serial,index=1,iobase=0x2f8,irq=3,baudbase=1000000000,chardev=glbridge"])
    if input_port is not None:
        if input_port == 0:
            with socket.socket() as reserve:
                reserve.bind(('127.0.0.1', 0))
                input_port = reserve.getsockname()[1]
        command.extend(['-chardev',
                        f'socket,id=nbtinput,host=127.0.0.1,port={input_port},server=on,wait=off,nodelay=on',
                        '-device', 'virtserialport,chardev=nbtinput,bus=vfast.0,nr=2,name=nbtinput' if input_virtio else
                        'isa-serial,index=1,iobase=0x2f8,irq=3,baudbase=1000000000,chardev=nbtinput'])
    bridge_type = NativeSocketRendererBridge if direct_renderer else SocketRendererBridge
    renderer_environment = {"MHI2_SHADER_CACHE": GRAPHICS / "host/shader-cache",
                            "MHI2_GL_FRAME": folder / "frame.ppm"}
    if dma_transport:
        renderer_environment['GLHOST_DMA_CONFIG'] = folder/'dma-config.txt'
    bridge = bridge_type(port, renderer, dll_dir=dll_dir,
                                  log_dir=folder / "relay", capture=capture_protocol,
                                  extra_env=renderer_environment)
    result = {"test": "ORIGINAL_NBT_HMI_RUNTIME_DIAGNOSTIC", "transport": transport,
              "source_ifs": str(source), "image": image, "run_directory": str(folder),
              "qemu_command": command, "observation_seconds": seconds,
              "protocol_capture_enabled": bool(capture_protocol),
              "graphics_virtio_port": virtio_port if transport == 'virtio' else None,
              "keyboard_hal": bool(keyboard_hal),
              "cpu_accelerator": accelerator,
              "renderer_transport": 'bounded_guest_dma' if dma_transport else 'native_socket' if direct_renderer else 'python_pipe_relay',
              "frame_publication": 'cached_rgb_block' if block_publication else 'legacy_pixel_writes',
              "collection_completed": False, "menu_verified": False}
    if input_port is not None:
        result['input_transport'] = {'host': '127.0.0.1', 'port': input_port,
                                     'guest_endpoint': 'virtio port2' if input_virtio else 'COM2/0x2f8',
                                     'protocol': 'Original length-framed MTP passthrough'}
        print('NBT_RUN_READY ' + json.dumps({'run_directory': str(folder),
                                              'input_port': input_port}), flush=True)
    (folder / 'run-info.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    if on_ready is not None:
        on_ready({'run_directory': str(folder), 'input_port': input_port,
                  'input_kind': 'virtio' if input_virtio else 'uart', 'keyboard_hal': keyboard_hal})
    process = None
    qmp = None
    started = time.monotonic()
    stop_reason = None
    crash_seen_at = None
    with monitor_path.open("wb") as monitor, stderr_path.open("wb") as stderr:
        try:
            process = subprocess.Popen(command, cwd=QEMU.parent, stdin=subprocess.PIPE,
                                       stdout=monitor, stderr=stderr,
                                       creationflags=subprocess.CREATE_NO_WINDOW)
            bridge.start(connect_timeout=min(10, seconds))
            qmp = QmpMonitor(monitor_port, folder / "monitor-qmp.jsonl")
            result['qemu_pid'] = process.pid
            if dma_transport:
                layout = qmp.command('human-monitor-command', {'command-line':'info ramblock'})
                (folder/'ramblock.txt').write_text(layout)
                match = re.search(r'^\s*pc\.ram\s+\d+\s+KiB\s+(0x[0-9a-f]+)\s+(0x[0-9a-f]+)\s+(0x[0-9a-f]+)\s+(0x[0-9a-f]+)\s+rw', layout, re.M|re.I)
                if not match or int(match[1],16) or int(match[2],16)!=0x20000000:
                    raise RuntimeError('DMA requires the explicit512MiB pc.ram mapping')
                created, ended, kernel_time, user_time = [ctypes.c_uint64() for _ in range(4)]
                get_times=ctypes.windll.kernel32.GetProcessTimes
                get_times.argtypes=[ctypes.c_void_p]*5
                get_times.restype=ctypes.c_int
                if not get_times(ctypes.c_void_p(int(process._handle)),ctypes.byref(created),
                                 ctypes.byref(ended),ctypes.byref(kernel_time),ctypes.byref(user_time)):
                    raise RuntimeError('Cannot identify owned QEMU process lifetime')
                config=folder/'dma-config.txt'
                temporary=config.with_suffix('.tmp')
                temporary.write_text(f'{process.pid} {int(match[4],16):x} {int(match[2],16):x} {created.value:x}\n')
                temporary.replace(config)
                result['dma_transport']={'ram_map_from_qmp':True,'qemu_pid':process.pid,
                    'guarded_adapter_allocation_only':True,'config':str(config)}
            (folder/'run-info.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
            deadline = started + seconds
            while True:
                serial = read_text(serial_path)
                hmi = classify_hmi(serial)
                now = time.monotonic()
                if stop_event is not None and stop_event.is_set():
                    stop_reason = 'requested_stop'
                    break
                if hmi["exit_code"] is not None:
                    stop_reason = "hmi_exit_recorded"
                    break
                if hmi["loader_fatal"]:
                    stop_reason = "guest_loader_fatal"
                    break
                if hmi["crash_signal"]:
                    if crash_seen_at is None:
                        crash_seen_at = now
                    if now - crash_seen_at >= 1:
                        stop_reason = "hmi_crash_without_exit_marker"
                        break
                if process.poll() is not None:
                    stop_reason = "qemu_exited"
                    break
                if bridge.process.poll() is not None:
                    stop_reason = "renderer_exited"
                    break
                if bridge.errors:
                    stop_reason = "relay_error"
                    break
                if now >= deadline:
                    stop_reason = "observation_limit"
                    break
                time.sleep(.025)
        except BaseException as error:
            stop_reason = "collector_error"
            result["collector_error"] = repr(error)
        finally:
            result["elapsed_until_stop"] = time.monotonic() - started
            # Freeze the guest before closing its display transport, so final
            # teardown does not generate an extra guest graphics failure.
            if process and process.poll() is None:
                try:
                    if qmp is None:
                        qmp = QmpMonitor(monitor_port, folder / "monitor-qmp.jsonl")
                    qmp.command("stop")
                    result["paused_vm_status"] = qmp.command("query-status")
                    for monitor_command in ("info registers", "info cpus", "info lapic", "info irq"):
                        snapshot = qmp.command("human-monitor-command", {"command-line": monitor_command})
                        monitor.write((snapshot or "").encode("utf-8"))
                    monitor.flush()
                except (OSError, ValueError, RuntimeError, EOFError) as error:
                    result["monitor_error"] = repr(error)
            try:
                result["relay"] = bridge.stop()
            except BaseException as error:
                result['relay_cleanup_error'] = repr(error)
                if bridge.process and bridge.process.poll() is None:
                    try:
                        bridge.process.terminate()
                        bridge.process.wait(timeout=3)
                    except (OSError, subprocess.TimeoutExpired):
                        bridge.process.kill()
                        bridge.process.wait(timeout=3)
                result['relay'] = {'errors': [repr(error)],
                                  'renderer_exit_code': bridge.process.returncode if bridge.process else None}
            finally:
                if process and process.poll() is None:
                    try:
                        if qmp is not None:
                            qmp.command("quit")
                        else:
                            process.terminate()
                        process.wait(timeout=3)
                    except (OSError, ValueError, RuntimeError, EOFError, subprocess.TimeoutExpired):
                        process.terminate()
                        try:
                            process.wait(timeout=3)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait(timeout=3)
                if process and process.stdin:
                    process.stdin.close()
                if qmp is not None:
                    qmp.close()
                result["qemu_exit_code"] = process.returncode if process else None
    serial = read_text(serial_path)
    result["stop_reason"] = stop_reason
    result["hmi"] = classify_hmi(serial, stop_reason == "observation_limit")
    if (stop_reason == 'requested_stop' and result['hmi']['process_observed'] and
        result['hmi']['exit_code'] is None and result['hmi']['crash_signal'] is None):
        result['hmi']['state'] = 'stopped_by_viewer'
    try:
        result["qnx_evidence"] = classify_qnx_evidence(source, serial, read_text(monitor_path))
        result["qnx_evidence"]["register_snapshot_available"] = bool(
            result["qnx_evidence"].get("observed_cr0"))
    except BaseException as error:
        result["qnx_evidence_error"] = repr(error)
    renderer_log = read_text(folder / "relay/renderer-stderr.log")
    final_frames = re.findall(r"glhost: client disconnected after (\d+) frames", renderer_log)
    interim_frames = re.findall(r"glhost: (\d+) frames swapped", renderer_log)
    result["graphics"] = {"commands": command_statistics(folder / "relay/guest-stream.bin") if capture_protocol
                          else {"protocol_capture_enabled": False},
                          "host_reported_presentations": int(final_frames[-1]) if final_frames else None,
                          "host_reported_presentations_lower_bound": max(map(int, interim_frames), default=0),
                          "menu_verified": False,
                          "frame": frame_details(folder / "frame.ppm")}
    result["captures"] = {name: fingerprint(path) for name, path in {
        "serial": serial_path, "guest_commands": folder / "relay/guest-stream.bin",
        "renderer_replies": folder / "relay/renderer-replies.bin",
        "renderer_log": folder / "relay/renderer-stderr.log"}.items()}
    result["collection_completed"] = bool(
        "collector_error" not in result and
        result.get("qnx_evidence", {}).get("qnx_kernel_execution_confirmed") and
        result["hmi"]["process_observed"] and
        stop_reason in ("hmi_exit_recorded", "hmi_crash_without_exit_marker", "observation_limit", "requested_stop"))
    result["infrastructure_fault"] = bool(stop_reason in (
        "collector_error", "relay_error", "renderer_exited", "qemu_exited") or
        result["relay"].get("errors") or
        result["relay"].get("renderer_exit_code") not in (0, None))
    result["elapsed_total_seconds"] = time.monotonic() - started
    result["serial"] = serial
    result["qemu_stderr"] = read_text(stderr_path)
    if not retain_boot_image and envelope.is_file():
        # This is the generated file owned by this completed run, never source firmware.
        envelope.unlink()
        result['temporary_boot_image_removed_after_vm_exit'] = True
    (folder / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ifs", type=Path, required=True)
    parser.add_argument("--seconds", type=int, choices=range(1, 121), default=30)
    parser.add_argument("--transport", choices=("virtio", "uart"), default="virtio")
    parser.add_argument('--input-port', type=int, default=None,
                        help='Expose VM COM2 on localhost for native MTP input; 0 chooses a free port')
    parser.add_argument('--synchronize-clock', action='store_true',
                        help='Use QEMU clock alignment for external input timing diagnostics')
    parser.add_argument('--no-icount', action='store_true',
                        help='Use the normal QEMU timer clock without instruction counting')
    parser.add_argument('--idle-sleep', action='store_true',
                        help='Keep icount but synchronize virtual idle waits with host time')
    parser.add_argument('--virtio-port', type=int, choices=(0, 1), default=0)
    parser.add_argument('--input-virtio', action='store_true')
    parser.add_argument('--icount-shift', type=int, default=6)
    args = parser.parse_args()
    result = run(args.ifs, args.seconds, args.transport, args.input_port, args.synchronize_clock,
                 not args.no_icount, idle_sleep=args.idle_sleep, virtio_port=args.virtio_port,
                 input_virtio=args.input_virtio, icount_shift=args.icount_shift)
    hmi = result["hmi"]
    print("Diagnostic collected: " + str(result["collection_completed"]), flush=True)
    print("Original QNX kernel: " + str(result.get("qnx_evidence", {}).get("qnx_kernel_execution_confirmed", False)), flush=True)
    print(f"HMI state: {hmi['state']}; exit={hmi['exit_code']}; crash={hmi['crash_signal']} at {hmi['crash_ip']}", flush=True)
    print("Renderer presentations: " + str(result["graphics"]["host_reported_presentations"]), flush=True)
    print("Menu verified: False (requires inspection of actual HMI output)", flush=True)
    print("Result: " + str(Path(result["run_directory"]) / "result.json"), flush=True)
    if not result["collection_completed"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
