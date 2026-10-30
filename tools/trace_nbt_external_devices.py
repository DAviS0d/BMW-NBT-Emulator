"""Bounded static instruction references for original NBT external-device hooks.

This reads ELF32 and the shipped PBA; it does not modify guest or firmware files.
Capstone instruction context is static evidence, not a proven runtime hook.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct

import capstone


def protobuf_fields(data, depth=0):
    """Decode wire structure only; field names remain unknown without schema."""
    def varint(offset):
        value = shift = 0
        while offset < len(data) and shift <= 63:
            byte = data[offset]
            offset += 1
            value |= (byte & 127) << shift
            if byte < 128:
                return value, offset
            shift += 7
        raise ValueError('Invalid varint')
    fields = []
    offset = 0
    while offset < len(data):
        start = offset
        tag, offset = varint(offset)
        number, wire = tag >> 3, tag & 7
        if not number:
            raise ValueError('Invalid protobuf field')
        if wire == 0:
            value, offset = varint(offset)
        elif wire == 2:
            size, offset = varint(offset)
            value = data[offset:offset+size]
            offset += size
            if len(value) != size:
                raise ValueError('Truncated field')
            if value and all(32 <= byte < 127 for byte in value):
                value = value.decode('ascii')
            elif depth < 12:
                try:
                    value = protobuf_fields(value, depth+1)
                except ValueError:
                    value = {'hex': value.hex()}
            else:
                value = {'hex': value.hex()}
        elif wire in (1, 5):
            size = 8 if wire == 1 else 4
            value = {'hex': data[offset:offset+size].hex()}
            offset += size
        else:
            raise ValueError('Unsupported protobuf wire type')
        fields.append({'field': number, 'wire': wire, 'offset': start, 'value': value})
    return fields


def find_component(fields, identifier):
    if any(x['field'] == 1 and x['value'] == identifier for x in fields):
        yield fields
    for field in fields:
        if isinstance(field['value'], list):
            yield from find_component(field['value'], identifier)


def sections(data):
    if data[:7] != b'\x7fELF\x01\x01\x01':
        raise ValueError('Expected ELF32 little-endian input')
    shoff = struct.unpack_from('<I', data, 32)[0]
    size, count, names_index = struct.unpack_from('<HHH', data, 46)
    records = [struct.unpack_from('<10I', data, shoff + index * size) for index in range(count)]
    names = records[names_index]
    table = data[names[4]:names[4]+names[5]]
    return [{'name': table[r[0]:].split(b'\0', 1)[0].decode('ascii', 'replace'),
             'type': r[1], 'flags': r[2], 'address': r[3], 'offset': r[4], 'size': r[5]}
            for r in records]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    target = args.root / 'outputs/native-integration/artifacts/boot/bin/HmiMain3D'
    pba = args.root / 'outputs/native-integration/artifacts/opt/hmi/data/ro/app/hmimultimedia/hmimultimediadrivesaudio.pba'
    data = target.read_bytes()
    sec = sections(data)
    executable = [item for item in sec if item['flags'] & 4]
    def address(offset):
        match = next((s for s in sec if s['type'] != 8 and s['offset'] <= offset < s['offset'] + s['size']), None)
        return match['address'] + offset - match['offset'] if match else None
    def file_offset(addr):
        match = next((s for s in sec if s['type'] != 8 and s['address'] <= addr < s['address'] + s['size']), None)
        return match['offset'] + addr - match['address'] if match else None
    decoder = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
    decoder.detail = True
    needles = ['updateUSB1Entry', 'updateUSB2Entry', 'updateBluetoothEntry',
               'updateWLANEntry', '::init all entries disabled', '::init setting notification',
               'onExternalDevicesSelectionFocused', 'CMultimediaExternalDevicesController.cpp']
    found = []
    for match in re.finditer(rb'[\x20-\x7e]{5,}\x00', data):
        text = match.group()[:-1].decode('ascii')
        if not any(needle in text for needle in needles):
            continue
        va = address(match.start())
        refs = []
        if va is not None:
            packed = struct.pack('<I', va)
            for code_section in executable:
                code = data[code_section['offset']:code_section['offset']+code_section['size']]
                position = code.find(packed)
                while position >= 0:
                    absolute = code_section['offset'] + position
                    # Validate an immediate-bearing instruction starts at this boundary.
                    validated = []
                    for back in range(1, 9):
                        begin = absolute - back
                        va_begin = address(begin)
                        if va_begin is None:
                            continue
                        instruction = next(decoder.disasm(data[begin:begin+15], va_begin, count=1), None)
                        if instruction and instruction.address + instruction.size >= address(absolute) + 4:
                            if any(op.type == capstone.x86.X86_OP_IMM and op.imm == va for op in instruction.operands):
                                validated.append({'address': hex(instruction.address),
                                                  'bytes': instruction.bytes.hex(),
                                                  'instruction': instruction.mnemonic + ' ' + instruction.op_str})
                    # Recover a likely function start only from common prologue bytes.
                    start = None
                    for signature in [b'\x55\x89\xe5', b'\x55\x8b\xec']:
                        candidate = data.rfind(signature, max(code_section['offset'], absolute-8192), absolute)
                        if candidate >= 0 and (start is None or candidate > start):
                            start = candidate
                    if start is None:
                        start = max(code_section['offset'], absolute-128)
                    context = []
                    context_end = min(code_section['offset']+code_section['size'], absolute+512)
                    for ins in decoder.disasm(data[start:context_end], address(start)):
                        if ins.address < address(absolute)-160:
                            continue
                        context.append({'address': hex(ins.address), 'bytes': ins.bytes.hex(),
                                        'instruction': ins.mnemonic + ' ' + ins.op_str})
                        if len(context) >= 180:
                            break
                    refs.append({'immediate_file_offset': absolute, 'immediate_address': hex(address(absolute)),
                                 'candidate_instruction_starts': validated,
                                 'nearest_standard_prologue': hex(address(start)),
                                 'context': context})
                    position = code.find(packed, position+1)
        found.append({'text': text, 'file_offset': match.start(), 'address': hex(va) if va else None,
                      'code_references': refs})
    pba_data = pba.read_bytes()
    pba_strings = [{'file_offset': m.start(), 'text': m.group().decode('ascii')}
                   for m in re.finditer(rb'[\x20-\x7e]{5,}', pba_data)]
    inventory = json.loads((args.root / 'outputs/native-integration/ifs-inventory.json').read_text())
    external_resource = next(x for x in inventory['imagefs']['entries']
                             if x.get('path') == 'opt/hmi/data/ro/app/hmimultimedia/hmimultimedia.pba')
    with Path(inventory['source']).open('rb') as stream:
        stream.seek(external_resource['absolute_offset'])
        external_data = stream.read(external_resource['size'])
    external_tree = protobuf_fields(external_data)
    components = list(find_component(external_tree, 0x6a58))
    row_summaries = []
    for component in components:
        for field in component:
            if field['field'] == 9 and isinstance(field['value'], list):
                for row in field['value']:
                    if row['field'] != 1 or not isinstance(row['value'], list):
                        continue
                    values = {item['field']: item['value'] for item in row['value']
                              if item['wire'] == 0}
                    row_summaries.append({'item_id': values.get(1),
                                          'field2_semantics_unknown_icon_candidate': values.get(2),
                                          'feature_id_inferred': values.get(3)})
    def disassemble_range(start, end):
        begin = file_offset(start)
        return [{'address': hex(ins.address), 'bytes': ins.bytes.hex(),
                 'instruction': ins.mnemonic + ' ' + ins.op_str}
                for ins in decoder.disasm(data[begin:begin+end-start], start)]
    vtable_address = 0x0945a530
    vtable_slots = {hex(slot): hex(struct.unpack_from('<I', data, file_offset(vtable_address+slot))[0])
                    for slot in (0x78, 0x7c, 0x8c, 0xc8)}
    callback_jump_table = [hex(struct.unpack_from('<I', data, file_offset(0x094fd704)+4*i)[0])
                           for i in range(11)]
    report = {'evidence_type': 'ordinary Python ELF parsing and Capstone static disassembly; not REA Evidence',
              'target': str(target), 'sha256': hashlib.sha256(data).hexdigest(),
              'executable_sections': executable, 'hooks': found,
              'pba': {'path': str(pba), 'size': len(pba_data),
                      'sha256': hashlib.sha256(pba_data).hexdigest(), 'header_hex': pba_data[:128].hex(),
                      'ascii_strings': pba_strings},
              'actual_external_devices_resource': {
                  'path': external_resource['path'], 'absolute_ifs_offset': external_resource['absolute_offset'],
                  'size': len(external_data), 'sha256': hashlib.sha256(external_data).hexdigest(),
                  'component_id': 0x6a58,
                  'matching_component_wire_fields': components,
                  'row_summaries': row_summaries,
                  'schema_status': 'Protobuf wire decoding; semantic field names inferred, not proven'},
              'native_list_analysis': {
                  'observed': [
                      'Init at 0x084572f8 calls 0x080ae8b0 with component ID0x6a58 and stores returned CHmiList in controller+0x7c',
                      'RTTI at0x0945a9a4 names CHmiList; primary vtable address0x0945a530',
                      'USB1 update passes itemID1 to list virtual slot+0x8c, then rejects index0xffffffff',
                      'Init registers callback0x08453b96 through signal returned by list virtual slot+0xc8',
                      'Callback reads item ID from fourth stack argument, subtracts1, rejects values greater than10, dispatches jump table',
                      'Resource component27224 has five row definitions with IDs1,2,4,11,5'],
                  'inferred': [
                      'Current row identities are USB1,USB2,Bluetooth,WLAN,AUX respectively',
                      'Row.field3 is a coding/feature ID: values align with original init feature checks',
                      'List slot+0x78 is setItem-like text update: arguments (list,labelObject,rowIndex,columnIndex)',
                      'List slot+0x7c enables/disables a row; slot+0x8c maps itemID to rowIndex',
                      'Row.field2 is likely icon ID; it is not established as a caption SID',
                      'Repeated row.field4 nested values likely represent label cells; semantic schema not recovered'],
                  'vtable_address': hex(vtable_address), 'vtable_slots': vtable_slots,
                  'selection_jump_table_address': '0x094fd704',
                  'selection_jump_table_item_ids_1_through_11': callback_jump_table,
                  'focused_disassembly': {
                      'controller_init': disassemble_range(0x084572f8, 0x0845750a),
                      'selection_callback': disassemble_range(0x08453b96, 0x08453c27),
                      'list_lookup': disassemble_range(0x080ae8b0, 0x080ae8ea),
                      'label_setter_prefix': disassemble_range(0x080b7c50, 0x080b7d00)},
                  'remaining_native_abi': [
                      'Recover exact protobuf message schema or prove all copied row fields and caption representation',
                      'Allocate or construct two valid native label objects for Android Auto and CarPlay; no ABI-safe constructor is yet proven for arbitrary UTF text',
                      'Choose nonconflicting item IDs and define feature-gating behavior for appended rows',
                      'Prove UI-thread ownership, callback signature and registration lifecycle before replacing/wrapping selection handling',
                      'Connect custom selections to an owned projection surface and input/audio focus; host JPEG alone is not native integration',
                      'Build a separate derived IFS with integrity metadata, retain originals and validate runtime row rendering/selection'],
                  'patch_status': 'No PBA, HmiMain3D, guest memory or firmware changes made'},
              'limits': ['No firmware changes or runtime hooks made',
                         'Nearby standard prologue is a candidate boundary, not function identity proof',
                         'Raw immediate matches require instruction/control-flow validation',
                         'No list item count or insertion API proven yet']}
    output = args.root / 'outputs/native-integration/external-device-hooks.json'
    output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({'report': str(output), 'string_count': len(found),
                      'reference_count': sum(len(x['code_references']) for x in found),
                      'pba_size': len(pba_data), 'pba_strings': len(pba_strings)}))


if __name__ == '__main__':
    main()
