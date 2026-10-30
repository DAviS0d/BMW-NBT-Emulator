# © 2026 davisod & JEtsKi
"""Bounded QEMU boot experiment for the recovered, original Intel NBT IFS.

This is a diagnostic loader experiment, not a working NBT emulator. It creates
an ELF Multiboot envelope so QEMU can enter the IFS's original x86 startup code
in protected mode. No guest disk, network, shared host folder or firmware write
is attached. The experiment captures CPU state, then shuts down after 5 seconds.
The default run time is 5 seconds; --seconds permits up to 30 seconds.
The loader's own serial message is explicitly not proof that QNX booted.
"""

import argparse
import ctypes
import hashlib
import json
import re
import struct
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WORKSPACE = ROOT.parent.parent


def classify_evidence(serial, monitor):
    combined = "\n".join(serial.values())
    cr0 = re.search(r"CR0=([0-9a-fA-F]+)", monitor)
    paging = bool(cr0 and int(cr0.group(1), 16) & 0x80000000)
    shell = ("CPU:X86 Release:6.5.0" in combined and
             "ORIGINAL_QNX_SHELL_RUNNING" in combined and "procnto-smp-instr" in combined)
    bmw_init = "Welcome QNX 6.5.0 INTEL - BMW NBT B069_C2" in combined and "sysinit:" in combined
    hmi_exit = re.findall(r"HMI_RUN_EXIT=(\d+)", combined)
    return {"qnx_kernel_execution_confirmed": paging and (shell or bmw_init),
            "qnx_serial_shell_confirmed": shell,
            "hmi_load_attempted": "HMI_ORIGINAL_RUN_TEST" in combined,
            "hmi_exit_code": int(hmi_exit[-1]) if hmi_exit else None,
            "nvidia_driver_reports_no_gpu": "No NVIDIA GPU found" in combined}


def qemu_clock_callback(apic_hz=1_000_000_000):
    """Calibrate TSC against the selected virtual LAPIC, not a guessed CPU rate.

    QEMU hw/intc/apic_common.c derives elapsed LAPIC ticks from virtual ns,
    shifted by the divider. TCG uses1GHz; WHPX kernel APIC uses the frequency
    reported by Windows. This callback only describes the explicit virtual PC.
    """
    if not isinstance(apic_hz, int) or not 1_000_000 <= apic_hz <= 4_000_000_000:
        raise ValueError('Virtual APIC frequency must fit the calibrated 32-bit adapter')
    c = bytearray(b"\x53\x56\x57")  # preserve ebx, esi, edi (cdecl)
    c.extend(b"\xc7\x05" + struct.pack("<II", 0xFEE003E0, 0xB))
    c.extend(b"\xc7\x05" + struct.pack("<II", 0xFEE00380, 0xFFFFFFFF))
    c.extend(b"\x0f\x31\x89\xc6\x89\xd7")  # rdtsc; save edx:eax
    loop = len(c)
    c.extend(b"\x8b\x1d" + struct.pack("<I", 0xFEE00390) + b"\xf7\xd3")
    c.extend(b"\x81\xfb" + struct.pack("<I", 10_000_000))
    c.extend(b"\x0f\x82" + struct.pack("<i", loop - (len(c) + 6)))
    c.extend(b"\x0f\x31\x29\xf0\x19\xfa")  # rdtsc; subtract saved value
    # The10-million-tick sample fits32bits at the supported CPU/APIC rates.
    # CPU_Hz = measured_TSC_delta * LAPIC_Hz / measured_LAPIC_delta.
    c.extend(b"\xb9" + struct.pack("<I", apic_hz) + b"\xf7\xe1\xf7\xf3")
    c.extend(b"\xa3" + struct.pack("<I", 0x219C10))
    c.extend(b"\xc7\x05" + struct.pack("<II", 0x219B70, apic_hz))
    c.extend(b"\x5f\x5e\x5b\xc3")
    return c


def make_envelope(source, output, provide_memory=False, memory_layout="legacy",
                  startup_max_cpus=None, qemu_clock_adapter=False, qemu_apic_hz=1_000_000_000):
    image = source.read_bytes()
    if image[:4] != bytes.fromhex("eb7eff00"):
        raise ValueError("Not the expected QNX startup header")
    if struct.unpack_from("<H", image, 10)[0] != 3:
        raise ValueError("This test only accepts the original x86 IFS")
    entry, physical = struct.unpack_from("<I", image, 12)[0], struct.unpack_from("<I", image, 20)[0]
    ram_size = struct.unpack_from("<I", image, 28)[0]
    code_base = 0x00100000
    code = bytearray(b"\xfa\xfc\xbc" + struct.pack("<I", 0x00090000))  # cli; cld; stack
    adapter_patches = []
    if qemu_clock_adapter:
        expected = "034c2c37f60b86c40eb43e77636a8d84903ee77d1f2df250cdd9a98b134cfe8b"
        if hashlib.sha256(image).hexdigest() != expected:
            reference = (ROOT / "btld_00001275/Intel/fs/sda2/appimage.ifs").read_bytes()
            startup_size = struct.unpack_from("<I", reference, 32)[0]
            if image[256:startup_size - 4] != reference[256:startup_size - 4]:
                raise ValueError("The adapter requires the analyzed original startup instructions")
        # Replace one chipset table DATA record in guest memory, retaining
        # its terminator and the original startup instruction stream.
        for address, value in ((0x219160, 0x12378086), (0x219164, 0)):
            code.extend(b"\xc7\x05" + struct.pack("<II", address, value))
        for address in (0x21916C, 0x219170):  # name and init callback
            code.extend(b"\xc7\x05" + struct.pack("<I", address))
            adapter_patches.append(len(code))
            code.extend(b"\0" * 4)
    if startup_max_cpus is not None:
        # Configure the documented QNX -P option in the startup's embedded
        # boot arguments in guest memory. Leave the source IFS on disk and
        # every instruction of the original startup unchanged.
        option = b"\x00-P2\x00"
        if image.count(option) != 1:
            raise ValueError("Expected one original -P2 boot argument")
        argument_offset = image.index(option) + 3
        code.extend(b"\xc6\x05" + struct.pack("<I", physical + argument_offset)
                    + str(startup_max_cpus).encode("ascii"))
    if provide_memory:
        # startup_info_mem entries in startup_header.info, supplied by an IPL.
        # Reserve the conventional PC BIOS/video hole between 0x9f000 and 1 MiB.
        if memory_layout == "nbt-map":
            # This startup first reads its vendor type 0x8004, then iterates
            # 8-byte records: address with low-byte type (0 = RAM), size.
            # See original startup at 0x20302d..0x2030b4. It only consumes the
            # first standard type-1 record, so the old low-first layout was
            # reporting less than 1 MiB as "RAM: 0 MB".
            high_start = 0x101000 if qemu_clock_adapter else 0x100000
            information = (struct.pack("<HHIIII", 0x8004, 20,
                                       0, 0x9F000, high_start, 0x20000000 - high_start)
                           + struct.pack("<I", 0))
        elif memory_layout == "high-first":
            information = (struct.pack("<HHII", 1, 12, 0x100000, 0x1FF00000)
                           + struct.pack("<HHII", 1, 12, 0, 0x9F000)
                           + struct.pack("<I", 0))
        else:
            information = (struct.pack("<HHII", 1, 12, 0, 0x9F000)
                           + struct.pack("<HHII", 1, 12, 0x100000, 0x1FF00000)
                           + struct.pack("<I", 0))
        for offset in range(0, len(information), 4):
            code.extend(b"\xc7\x05" + struct.pack("<I", physical + 64 + offset)
                        + information[offset:offset + 4])
    for port, value in ((0x3FB, 0x80), (0x3F8, 1), (0x3F9, 0), (0x3FB, 3)):
        code.extend(b"\x66\xba" + struct.pack("<H", port) + b"\xb0" + bytes([value]) + b"\xee")
    code.append(0xBE)  # mov esi, message
    message_patch = len(code)
    code.extend(b"\x00" * 4)
    code.extend(b"\x66\xba\xf8\x03")
    loop = len(code)
    code.extend(b"\xac\x84\xc0\x74\x00\xee\xeb\x00")
    done = len(code)
    code[loop + 4] = done - (loop + 5)
    code[loop + 7] = (loop - (loop + 8)) & 255
    code.extend(b"\x31\xc0\x31\xdb\xba" + struct.pack("<I", entry) + b"\xff\xe2")
    message_at = code_base + len(code)
    struct.pack_into("<I", code, message_patch, message_at)
    code.extend(b"NBT diagnostic loader: entering ORIGINAL QNX startup; QNX boot is not confirmed.\r\n\0")
    if qemu_clock_adapter:
        label_address = code_base + len(code)
        code.extend(b"QEMU virtual-PC clock adapter\0")
        callback_address = code_base + len(code)
        code.extend(qemu_clock_callback(qemu_apic_hz))
        struct.pack_into("<I", code, adapter_patches[0], label_address)
        struct.pack_into("<I", code, adapter_patches[1], callback_address)
    if len(code) > 0x1000:
        raise ValueError("Loader and adapter must fit in the reserved 4 KiB page")
    elf = bytearray(0x2000 + len(image))
    identification = b"\x7fELF\x01\x01\x01" + b"\x00" * 9
    struct.pack_into("<16sHHIIIIIHHHHHH", elf, 0, identification, 2, 3, 1,
                     code_base, 52, 0, 0, 52, 32, 2, 40, 0, 0)
    struct.pack_into("<8I", elf, 52, 1, 0x1000, code_base, code_base,
                     len(code), 0x1000, 5, 0x1000)
    struct.pack_into("<8I", elf, 84, 1, 0x2000, physical, physical,
                     len(image), max(ram_size, len(image)), 7, 0x1000)
    magic, flags = 0x1BADB002, 3
    struct.pack_into("<3I", elf, 0x100, magic, flags, -(magic + flags) & 0xFFFFFFFF)
    elf[0x1000:0x1000 + len(code)] = code
    elf[0x2000:] = image
    output.write_bytes(elf)
    return {"entry": hex(entry), "physical_address": hex(physical),
            "ipl_memory_info_supplied": provide_memory,
            "ipl_memory_layout": memory_layout if provide_memory else None,
            "startup_max_cpus_override": startup_max_cpus,
            "qemu_clock_adapter": qemu_clock_adapter,
            "qemu_apic_hz": qemu_apic_hz if qemu_clock_adapter else None,
            "ram_size": ram_size, "source_sha256": hashlib.sha256(image).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provide-memory", action="store_true",
                        help="Supply QNX IPL memory records for the virtual PC")
    parser.add_argument("--memory-layout", choices=("legacy", "high-first", "nbt-map"),
                        default="legacy", help="Experimental IPL memory description")
    parser.add_argument("--smp", type=int, choices=(1, 2), default=1,
                        help="Number of virtual CPUs; original startup requests two")
    parser.add_argument("--startup-max-cpus", type=int, choices=(1, 2),
                        help="Override original startup -P boot argument in guest memory")
    parser.add_argument("--qemu-clock-adapter", action="store_true",
                        help="Experimental virtual-PC table/callback port; not NBT hardware emulation")
    parser.add_argument("--ifs", type=Path, help="Explicit custom local IFS variant to test")
    parser.add_argument("--seconds", type=int, choices=range(1, 31), default=5,
                        help="Bounded wall-clock run time, maximum 30 seconds")
    parser.add_argument("--icount-shift", type=int, choices=range(0, 9), default=0,
                        help="Virtual ns per guest instruction = 2**shift in adapter mode")
    parser.add_argument("--trace-kd-init", action="store_true",
                        help="Trace only the observed libKD initialization and HMI kdMain address ranges")
    args = parser.parse_args()
    if args.qemu_clock_adapter and not (args.provide_memory and args.memory_layout == "nbt-map"
                                       and args.smp == 1 and args.startup_max_cpus == 1):
        parser.error("--qemu-clock-adapter requires --provide-memory --memory-layout nbt-map --smp 1 --startup-max-cpus 1")
    # Avoid interactive Windows error dialogs when checking portable dependencies.
    ctypes.windll.kernel32.SetErrorMode(0x0001 | 0x0002 | 0x8000)
    tool_root = WORKSPACE / "work" / "emulation-tools" / "qemu-portable"
    matches = list(tool_root.rglob("qemu-system-i386.exe"))
    if len(matches) != 1:
        raise FileNotFoundError("Expected one portable qemu-system-i386.exe")
    qemu = matches[0]
    source = args.ifs.resolve() if args.ifs else ROOT / "btld_00001275/Intel/fs/sda2/appimage.ifs"
    number = 1
    while (ROOT / f"boot_test_{number:02d}").exists():
        number += 1
    folder = ROOT / f"boot_test_{number:02d}"
    folder.mkdir(exist_ok=False)
    envelope = folder / "nbt_original_ifs_multiboot.elf"
    metadata = make_envelope(source, envelope, args.provide_memory, args.memory_layout,
                             args.startup_max_cpus, args.qemu_clock_adapter)
    version = subprocess.run([str(qemu), "--version"], capture_output=True, text=True,
                             creationflags=subprocess.CREATE_NO_WINDOW, check=True).stdout
    command = [str(qemu), "-machine", "pc", "-accel", "tcg", "-cpu", "qemu32",
               "-m", "512M", "-smp", str(args.smp), "-kernel", str(envelope),
               "-display", "none", "-serial", "file:" + str(folder / "serial_com1.log"),
               "-serial", "file:" + str(folder / "serial_com2.log"),
               "-monitor", "stdio", "-nic", "none", "-no-reboot", "-no-shutdown",
               "-d", "cpu_reset", "-D", str(folder / "cpu_reset.log")]
    if args.qemu_clock_adapter:
        command[command.index("tcg")] = "tcg,thread=single"
        command.extend(["-icount", f"shift={args.icount_shift},sleep=off"])
    if args.trace_kd_init:
        command[command.index("cpu_reset")] = "cpu_reset,in_asm"
        command.extend(["-dfilter", "0xb8206380..0xb8206aaf,0x809fff4..0x80a0022"])
    process = subprocess.Popen(command, cwd=qemu.parent, stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, creationflags=subprocess.CREATE_NO_WINDOW)
    time.sleep(args.seconds)
    try:
        stdout, stderr = process.communicate("info registers\ninfo cpus\ninfo lapic\ninfo irq\nxp /1wx 0x219b70\nxp /1wx 0x219c10\nquit\n", timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        stdout, stderr = process.communicate()
    (folder / "monitor.log").write_text(stdout, encoding="utf-8")
    (folder / "stderr.log").write_text(stderr, encoding="utf-8")
    serial = {}
    for port in (1, 2):
        serial_path = folder / f"serial_com{port}.log"
        serial[str(port)] = serial_path.read_text(errors="replace") if serial_path.exists() else ""
    match = re.search(r"EIP=([0-9a-fA-F]+)", stdout)
    result = {
        "status": "EXPERIMENT_ONLY_NOT_A_WORKING_NBT_EMULATOR", "qemu_version": version,
        "image": metadata, "command": command, "exit_code": process.returncode,
        "observed_eip": match.group(1) if match else None,
        "serial": serial, "stderr": stderr,
        "original_qnx_welcome_seen": any("Welcome QNX" in s for s in serial.values()),
        "custom_ifs_variant": args.ifs is not None,
        "original_hmi_rendered": False,
        "note": "The original IFS file remains unchanged. Optional guest-memory changes are recorded in image metadata: IPL fields, -P boot argument, and/or the experimental QEMU chipset table/clock callback port. This is not complete NBT hardware emulation. The loader serial announcement is not QNX output.",
    }
    result.update(classify_evidence(serial, stdout))
    (folder / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2), flush=True)


if __name__ == "__main__":
    main()
