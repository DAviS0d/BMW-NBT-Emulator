"""Offline regression checks for the pinned native sports detour contract.

Run with the analysis Python containing capstone:
    python tools/test_native_sports_contract.py
Does not load, execute, or patch HmiMain3D.
"""
import hashlib
import re
import struct
import unittest
from pathlib import Path

import capstone

ROOT = Path(__file__).resolve().parents[1]
HMI = ROOT / 'outputs/native-integration/artifacts/boot/bin/HmiMain3D'
SOURCE = ROOT / 'work/bridge-v2/guest/native_sports.c'
EXPECTED_SHA = '554b67d4d6317cfb1715d544874fae8ddd2c975be503c9e2514e2dc2f3a0d693'


class NativeSportsContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = HMI.read_bytes()
        cls.source = SOURCE.read_text(encoding='utf-8')
        if hashlib.sha256(cls.data).hexdigest() != EXPECTED_SHA:
            raise AssertionError('The hook address contract requires the exact analyzed HMI SHA-256')
        cls.decoder = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        cls.segments = []
        phoff = struct.unpack_from('<I', cls.data, 28)[0]
        entsize, count = struct.unpack_from('<HH', cls.data, 42)
        for index in range(count):
            kind, offset, address, physical, size, memsize, flags, align = struct.unpack_from('<8I', cls.data, phoff + index * entsize)
            if kind == 1:
                cls.segments.append((offset, address, size))

    def read(self, address, length):
        for offset, virtual, size in self.segments:
            if virtual <= address and address + length <= virtual + size:
                start = offset + address - virtual
                return self.data[start:start + length]
        self.fail(f'Address outside mapped file bytes: {address:x}+{length}')

    def instruction(self, address):
        return next(self.decoder.disasm(self.read(address, 15), address))

    def test_hook_identities_match_source_and_complete_instructions(self):
        definitions = dict(re.findall(r'#define\s+(SPORTS_(?:INIT|DTOR0|DTOR1|AVAILABILITY))\s+(0x[0-9A-Fa-f]+)u', self.source))
        hooks = re.findall(r'\{\s*(SPORTS_(?:INIT|DTOR0|DTOR1|AVAILABILITY)),\s*\{([^}]+)\}', self.source)
        self.assertEqual(len(hooks), 4)
        for name, identity_text in hooks:
            with self.subTest(hook=name):
                identity = bytes(int(token, 16) for token in re.findall(r'0x([0-9a-fA-F]{2})', identity_text))
                self.assertEqual(len(identity), 16)
                address = int(definitions[name], 16)
                self.assertEqual(self.read(address, 16), identity)
                instructions = list(self.decoder.disasm(identity[:5], address))
                self.assertEqual(sum(i.size for i in instructions), 5, 'The detour must not split an instruction')
                self.assertEqual([i.mnemonic for i in instructions], ['push', 'mov', 'push', 'push'])
                self.assertEqual(instructions[0].op_str, 'ebp')
                self.assertEqual(instructions[1].op_str, 'ebp, esp')
                self.assertNotIn('call', [i.mnemonic for i in instructions])
                self.assertNotIn('jmp', [i.mnemonic for i in instructions])

    def test_trampoline_replays_stack_prologue_then_returns_to_next_instruction(self):
        # Model exactly the bytes emitted by native_sports.c. Relative branches
        # in the displaced prologue would need relocation and are disallowed.
        for original in (0x088D3FD0, 0x088D4484, 0x088D452E, 0x088D0B72):
            trampoline_address = 0x30000000
            prologue = self.read(original, 5)
            delta = (original + 5 - (trampoline_address + 10)) & 0xffffffff
            trampoline = prologue + b'\xe9' + struct.pack('<I', delta)
            instructions = list(self.decoder.disasm(trampoline, trampoline_address))
            self.assertEqual(len(instructions), 5)
            self.assertEqual(instructions[-1].mnemonic, 'jmp')
            self.assertEqual(int(instructions[-1].op_str, 16), original + 5)
            self.assertEqual(instructions[0].mnemonic, 'push')
            self.assertEqual(instructions[1].op_str, 'ebp, esp')
            self.assertEqual(sum(i.mnemonic == 'push' for i in instructions), 3)

    def test_original_setter_identity_and_percentage_bound(self):
        match = re.search(r'helper_identity\[16\]\s*=\s*\{([^}]+)\}', self.source)
        self.assertIsNotNone(match)
        identity = bytes(int(token, 16) for token in re.findall(r'0x([0-9a-fA-F]{2})', match.group(1)))
        self.assertEqual(self.read(0x0934DE0E, 16), identity)
        instruction = self.instruction(0x0934DD48)
        self.assertEqual((instruction.mnemonic, instruction.op_str), ('cmp', 'dword ptr [ebp + 0xc], 0x64'))
        self.assertEqual(struct.unpack('<f', self.read(0x0944E860, 4))[0], 100.0)
        self.assertEqual(self.instruction(0x0934DE26).op_str, 'eax, dword ptr [eax + 8]')
        self.assertEqual(self.instruction(0x0934DE2B).op_str, 'eax, dword ptr [eax + 0xc]')

    def test_channel_zero_power_channel_one_torque_from_native_units_handler(self):
        # The first unit branch references the power-specific error string and
        # passes channel0 to the common label setter; the second does torque/1.
        cases = [(0x088D4A0E, 0x095F75B7, b'invalid power unit', 0x088D4A3E, '0'),
                 (0x088D4AD6, 0x095F760A, b'invalid torque unit', 0x088D4B06, '1')]
        for error_push, error_string, expected_text, channel_push, channel in cases:
            with self.subTest(channel=channel):
                instruction = self.instruction(error_push)
                self.assertEqual(instruction.mnemonic, 'push')
                self.assertEqual(int(instruction.op_str, 16), error_string)
                self.assertIn(expected_text, self.read(error_string, 90).split(b'\0')[0])
                instruction = self.instruction(channel_push)
                self.assertEqual((instruction.mnemonic, instruction.op_str), ('push', channel))
        for call_address in (0x088D4A44, 0x088D4B0C):
            instruction = self.instruction(call_address)
            self.assertEqual((instruction.mnemonic, instruction.op_str), ('call', '0x934da24'))


if __name__ == '__main__':
    unittest.main()
