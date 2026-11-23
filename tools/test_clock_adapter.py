"""Execute the generated x86 clock adapter with synthetic counters (no firmware).

Requires Unicorn: py -3 -m pip install unicorn
Run: py -3 tools/test_clock_adapter.py -v
"""
import importlib.util
from pathlib import Path
import random
import struct
import unittest

from unicorn import Uc, UcError, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE, UC_ERR_EXCEPTION
from unicorn.x86_const import (
    UC_X86_REG_EAX, UC_X86_REG_EBX, UC_X86_REG_ECX, UC_X86_REG_EDX,
    UC_X86_REG_ESI, UC_X86_REG_EDI, UC_X86_REG_EBP, UC_X86_REG_ESP,
    UC_X86_REG_EIP,
)

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    'clock_boot', ROOT / 'outputs/NBT_emulation_research/boot_experiment.py')
boot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(boot)

UINT32_MAX = (1 << 32) - 1
UINT64_MAX = (1 << 64) - 1


class ClockAdapterTests(unittest.TestCase):
    def test_original_division_faults_at_4_3_ghz(self):
        emulator = Uc(UC_ARCH_X86, UC_MODE_32)
        emulator.mem_map(0x100000, 4096)
        # Original mul ecx; div ebx with a 50 ms sample of a 4.3 GHz TSC.
        emulator.mem_write(0x100000, b'\xf7\xe1\xf7\xf3')
        emulator.reg_write(UC_X86_REG_EAX, 215_000_000)
        emulator.reg_write(UC_X86_REG_ECX, 200_000_000)
        emulator.reg_write(UC_X86_REG_EBX, 10_000_000)
        with self.assertRaises(UcError) as error:
            emulator.emu_start(0x100000, 0x100004)
        self.assertEqual(error.exception.errno, UC_ERR_EXCEPTION)
        self.assertEqual(emulator.reg_read(UC_X86_REG_EIP), 0x100002)

    def execute(self, apic_hz, elapsed_apic, elapsed_tsc, start_tsc=123456789):
        emulator = Uc(UC_ARCH_X86, UC_MODE_32)
        code_base, return_address, stack, qtime = 0x100000, 0x100F00, 0x90000, 0x300000
        for address, size in ((code_base, 4096), (0x80000, 0x20000),
                              (0x200000, 0x20000), (qtime, 4096), (0xFEE00000, 4096)):
            emulator.mem_map(address, size)
        emulator.mem_write(code_base, bytes(boot.qemu_clock_callback(apic_hz)))
        emulator.mem_write(boot.QTIME_FREQUENCY_ADDRESS, boot.QTIME_FREQUENCY_INSTRUCTIONS)
        emulator.mem_write(boot.CPU_FREQUENCY_ADDRESS + 4, b'KEEP')
        emulator.mem_write(0xFEE00390, struct.pack('<I', UINT32_MAX - elapsed_apic))
        emulator.mem_write(stack, struct.pack('<I', return_address))
        emulator.reg_write(UC_X86_REG_ESP, stack)
        preserved = {UC_X86_REG_EBX: 0x12345678, UC_X86_REG_ESI: 0x23456789,
                     UC_X86_REG_EDI: 0x34567890, UC_X86_REG_EBP: 0x456789AB}
        for register, value in preserved.items():
            emulator.reg_write(register, value)
        samples = iter((start_tsc, (start_tsc + elapsed_tsc) & UINT64_MAX))
        reads = []

        def clock_read(machine, address, size, _):
            if machine.mem_read(address, 2) == b'\x0f\x31':
                value = next(samples)
                reads.append(value)
                machine.reg_write(UC_X86_REG_EAX, value & UINT32_MAX)
                machine.reg_write(UC_X86_REG_EDX, value >> 32)
                machine.reg_write(UC_X86_REG_EIP, address + 2)

        emulator.hook_add(UC_HOOK_CODE, clock_read)
        emulator.emu_start(code_base, return_address, count=1000)
        self.assertEqual(emulator.reg_read(UC_X86_REG_EIP), return_address)
        self.assertEqual(len(reads), 2)
        self.assertEqual(emulator.reg_read(UC_X86_REG_ESP), stack + 4)
        for register, value in preserved.items():
            self.assertEqual(emulator.reg_read(register), value)

        expected = elapsed_tsc * apic_hz // elapsed_apic
        self.assertEqual(struct.unpack('<I', emulator.mem_read(boot.CPU_FREQUENCY_ADDRESS, 4))[0],
                         min(expected, UINT32_MAX))
        self.assertEqual(emulator.mem_read(boot.CPU_FREQUENCY_ADDRESS + 4, 4), b'KEEP')
        self.assertEqual(struct.unpack('<I', emulator.mem_read(boot.APIC_FREQUENCY_ADDRESS, 4))[0], apic_hz)

        # Execute the adapted original store block, not just the arithmetic.
        # Both halves of the value that QNX actually consumes must survive.
        emulator.reg_write(UC_X86_REG_EBX, qtime)
        emulator.mem_write(qtime + 0x3C, struct.pack('<I', 0x80))
        emulator.emu_start(boot.QTIME_FREQUENCY_ADDRESS,
                          boot.QTIME_FREQUENCY_ADDRESS + len(boot.QTIME_FREQUENCY_INSTRUCTIONS), count=20)
        self.assertEqual(struct.unpack('<Q', emulator.mem_read(qtime, 8))[0], expected)
        self.assertEqual(struct.unpack('<I', emulator.mem_read(qtime + 0x3C, 4))[0], 0x81)

    def test_frequency_boundaries_and_long_samples(self):
        # A one-second sample makes the expected rate exact, including the
        # boundary whose low half is zero and samples exceeding 32 bits.
        for apic_hz in (200_000_000, 1_000_000_000):
            for frequency in (1_000_000_000, 3_200_000_000, UINT32_MAX,
                              1 << 32, (1 << 32) + 1, 4_300_000_000,
                              5_000_000_000, 10_000_000_000):
                with self.subTest(apic_hz=apic_hz, frequency=frequency):
                    self.execute(apic_hz, apic_hz, frequency)

    def test_normal_sample_and_counter_wrap(self):
        for apic_hz in (200_000_000, 1_000_000_000):
            for frequency in (3_200_000_000, 4_300_000_000, 6_000_000_000):
                with self.subTest(apic_hz=apic_hz, frequency=frequency):
                    self.execute(apic_hz, 10_000_000,
                                 frequency * 10_000_000 // apic_hz,
                                 start_tsc=UINT64_MAX - 100)

    def test_full_product_against_python_integer_arithmetic(self):
        generator = random.Random(20261123)
        for _ in range(80):
            apic_hz = generator.randint(1_000_000, 4_000_000_000)
            elapsed_apic = generator.randint(10_000_000, UINT32_MAX)
            frequency = generator.randint(100_000_000, 100_000_000_000)
            elapsed_tsc = frequency * elapsed_apic // apic_hz
            with self.subTest(apic_hz=apic_hz, elapsed_tsc=elapsed_tsc):
                self.execute(apic_hz, elapsed_apic, elapsed_tsc)

    def test_rejects_changed_or_truncated_startup_instructions(self):
        physical = boot.QTIME_FREQUENCY_ADDRESS
        original = boot.QTIME_FREQUENCY_INSTRUCTIONS
        boot.validate_qtime_frequency_adapter(original, physical)
        for offset in range(len(original)):
            modified = bytearray(original)
            modified[offset] ^= 1
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                boot.validate_qtime_frequency_adapter(modified, physical)
        for image, address in ((b'', physical), (original[:-1], physical),
                               (original, physical + 1)):
            with self.assertRaises(ValueError):
                boot.validate_qtime_frequency_adapter(image, address)

    def test_invalid_apic_frequency(self):
        for frequency in (0, -1, 999_999, 4_000_000_001, 1.5):
            with self.subTest(frequency=frequency), self.assertRaises(ValueError):
                boot.qemu_clock_callback(frequency)


if __name__ == '__main__':
    unittest.main()
