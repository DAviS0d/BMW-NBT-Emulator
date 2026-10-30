"""Static, bounded x86 sports-display anchor tracing; never executes the HMI."""
import argparse
import hashlib
import json
import re
import struct
from pathlib import Path
import capstone

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_HMI = ROOT / 'outputs/native-integration/artifacts/boot/bin/HmiMain3D'
EXPECTED_SHA256 = '554b67d4d6317cfb1715d544874fae8ddd2c975be503c9e2514e2dc2f3a0d693'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--hmi', type=Path, default=DEFAULT_HMI)
    parser.add_argument('--report', type=Path, default=ROOT / 'outputs/native-integration/sports-hooks.json')
    args = parser.parse_args()
    data = args.hmi.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != EXPECTED_SHA256:
        parser.error('This address trace is pinned to the extracted NBT HMI SHA-256 ' + EXPECTED_SHA256)
    if data[:6] != b'\x7fELF\x01\x01':
        raise ValueError('Expected little-endian ELF32')
    phoff = struct.unpack_from('<I', data, 28)[0]
    phentsize, phnum = struct.unpack_from('<HH', data, 42)
    segments = []
    for i in range(phnum):
        kind, offset, virtual, physical, filesz, memsz, flags, align = struct.unpack_from('<8I', data, phoff + i * phentsize)
        if kind == 1:
            segments.append({'offset': offset, 'virtual': virtual, 'filesz': filesz, 'flags': flags})
    shoff = struct.unpack_from('<I', data, 32)[0]
    shentsize, shnum = struct.unpack_from('<HH', data, 46)
    executable_sections = []
    for i in range(shnum):
        section = struct.unpack_from('<10I', data, shoff + i * shentsize)
        if section[2] & 4:
            executable_sections.append((section[4], section[5]))
    def va(offset):
        return next((s['virtual'] + offset - s['offset'] for s in segments if s['offset'] <= offset < s['offset'] + s['filesz']), None)
    def executable(offset):
        return any(start <= offset < start + size for start, size in executable_sections)
    decoder = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
    decoder.skipdata = True
    anchors = [b'CVehSportInstrumentsTable.cpp', b'CVehSportInstrumentsTable::onNewCurrentUnitsStatusExt:',
               b'25CVehSportInstrumentsTable', b'N11CPxyVehicle19CActualValueTorque2E',
               b'N11CPxyVehicle13CEngineSpeed2E', b'hmi_sportInstruments_update',
               b'CHmiSportInstrument2DHelper.cpp', b'engine.torque']
    report = {'artifact': str(args.hmi.resolve()), 'sha256': digest,
              'kind': 'static_byte_references_and_x86_disassembly', 'anchors': [],
              'limits': ['A 32-bit value match alone is not a verified code cross-reference.',
                         'Disassembly windows are heuristic and may begin inside an instruction.',
                         'No function calling convention, object lifetime, model layout, or runtime behavior is verified.']}
    for needle in anchors:
        for match in re.finditer(re.escape(needle), data):
            start = match.start()
            while start and 32 <= data[start - 1] <= 126:
                start -= 1
            end = match.end()
            while end < len(data) and 32 <= data[end] <= 126:
                end += 1
            if end < 0 or end - start > 1024:
                continue
            address = va(start)
            if address is None:
                continue
            references = []
            for ref in re.finditer(re.escape(struct.pack('<I', address)), data):
                offset = ref.start()
                record = {'file_offset': offset, 'virtual_address': hex(va(offset)) if va(offset) is not None else None,
                          'in_executable_segment': executable(offset)}
                if executable(offset):
                    # Start at the nearest common GCC frame prologue if nearby.
                    prologue = data.rfind(b'\x55\x89\xe5', max(0, offset - 800), offset)
                    window_start = prologue if prologue >= 0 else max(0, offset - 40)
                    record['window_start'] = hex(va(window_start))
                    record['prologue_found'] = prologue >= 0
                    record['disassembly'] = [{'address': hex(i.address), 'bytes': i.bytes.hex(), 'mnemonic': i.mnemonic, 'operands': i.op_str}
                                             for i in decoder.disasm(data[window_start:offset + 130], va(window_start))]
                else:
                    record['nearby_words'] = [hex(x) for x in struct.unpack_from('<' + 'I' * 12, data, max(0, offset - 16))]
                references.append(record)
            report['anchors'].append({'needle': needle.decode(), 'text': data[start:end].decode('utf-8', errors='replace'),
                                      'file_offset': start, 'virtual_address': hex(address), 'references': references})
    def offset_for(address):
        return next((s['offset'] + address - s['virtual'] for s in segments
                     if s['virtual'] <= address < s['virtual'] + s['filesz']), None)
    # Candidate Itanium vtable inferred from offset-to-top, RTTI, and code slots.
    # Keep raw words so the structural inference can be independently reviewed.
    report['candidate_vtable'] = {'address': '0x95f7668', 'rtti': '0x95f76b8',
                                  'basis': 'Zero offset-to-top at 0x95f7660; RTTI pointer at 0x95f7664; RTTI name points at CVehSportInstrumentsTable string.'}
    report['float_constants'] = [{'address': hex(address), 'value': struct.unpack_from('<f', data, offset_for(address))[0]}
                                 for address in (0x944e860, 0x95365e0)]
    methods = [0x88d3be2, 0x88d3c38, 0x88d3cc0, 0x88d3d92, 0x88d3de0, 0x88d3e7a, 0x88d3f10, 0x88d3fd0,
               0x88d447c, 0x88d4484, 0x88d4527, 0x88d452e, 0x88d499a, 0x88d4b58,
               0x8cc5214, 0x8cc524a, 0x8cc536a, 0x8cc53a4, 0x934de0e, 0x934e4a8,
               0x934dd3c, 0x934e466]
    report['candidate_methods'] = []
    for address in methods:
        offset = offset_for(address)
        instructions = []
        for instruction in decoder.disasm(data[offset:offset + 1900], address):
            instructions.append({'address': hex(instruction.address), 'bytes': instruction.bytes.hex(),
                                 'mnemonic': instruction.mnemonic, 'operands': instruction.op_str})
            if instruction.mnemonic in ('ret', 'retf'):
                break
            if instruction.mnemonic == 'jmp' and len(instructions) >= 2 and instructions[-2]['mnemonic'] in ('leave', 'pop'):
                break
        report['candidate_methods'].append({'address': hex(address), 'file_offset': offset,
                                            'first_return_bounded_disassembly': instructions})
    report['findings'] = [
        {'claim': 'Sport-table subscription method registers two data callbacks and one unit callback.',
         'evidence': ['0x088d3f10', '0x088d3f38', '0x088d3f55', '0x088d3f72'],
         'observed_arguments': {'proxy_pointer': 'table+0x60', 'callbacks': ['0x088d3cc0', '0x088d3c38', '0x088d499a']}},
        {'claim': 'Value callback reads two bytes from a proxy property, rejects 0xff, then updates channels 0/1.',
         'evidence': ['0x088d3c38', '0x08cc5214', '0x08cc524a'],
         'observed_arguments': {'proxy_property': '*(table+0x60)+0x3474', 'helper_pointer': '*(table+0x38)',
                                'byte_fields': ['property+0x7d', 'property+0x7c'], 'update_wrapper': '0x0934de0e'}},
        {'claim': 'Original value wrapper selects channel tube then forwards an integer percentage to animation code.',
         'evidence': ['0x0934de0e', '0x0934dd3c', '0x0934dd48'],
         'observed_arguments': {'stack_arguments_in_call_order': ['helper_instance', 'value_0_to_100', 'channel_0_or_1'],
                                'tube_pointers': ['helper+8', 'helper+0xc']},
         'inference': 'Caller cleanup and ebp-based argument access are consistent with an x86 cdecl-style function; no runtime invocation verified.'},
    ]
    report['unresolved'] = ['How to acquire the live sport-table/helper instance safely.',
                            'Required HMI thread and lifecycle for invoking the model/animation update.',
                            'Which channel denotes power versus torque, and the physical-value scaling.',
                            'Proxy producer ABI, validity flags, notification serialization, and update synchronization.',
                            'No callable exported setter was established; fixed addresses are pinned to this artifact hash.']
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'report': str(args.report), 'anchors': [{'text': a['text'], 'address': a['virtual_address'],
          'references': [r['virtual_address'] for r in a['references']]} for a in report['anchors']]}, indent=2))


if __name__ == '__main__':
    main()
