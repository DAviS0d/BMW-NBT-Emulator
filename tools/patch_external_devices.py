"""Append two experimental rows to the original NBT external-devices list.

Native label/selection hooks in native_devices.c are required. This never changes
the source file or IFS: it writes a separate resource for the experimental packer.
"""
import argparse
import hashlib
import json
from pathlib import Path


def varint(value):
    result = bytearray()
    while value >= 128:
        result.append((value & 127) | 128)
        value >>= 7
    result.append(value)
    return bytes(result)


def read_varint(data, offset):
    value = shift = 0
    while offset < len(data) and shift <= 63:
        byte = data[offset]
        offset += 1
        value |= (byte & 127) << shift
        if byte < 128:
            return value, offset
        shift += 7
    raise ValueError('Invalid protobuf varint')


def fields(data):
    offset = 0
    while offset < len(data):
        begin = offset
        tag, offset = read_varint(data, offset)
        number, wire = tag >> 3, tag & 7
        if number == 0:
            raise ValueError('Invalid protobuf field number')
        if wire == 0:
            value, offset = read_varint(data, offset)
        elif wire == 2:
            size, offset = read_varint(data, offset)
            value = data[offset:offset+size]
            offset += size
            if len(value) != size:
                raise ValueError('Truncated protobuf message')
        elif wire in (1, 5):
            size = 8 if wire == 1 else 4
            value = data[offset:offset+size]
            offset += size
            if len(value) != size:
                raise ValueError('Truncated protobuf fixed field')
        else:
            raise ValueError('Unsupported protobuf wire type')
        yield number, wire, value, data[begin:offset]


def message_field(number, payload):
    return varint(number * 8 + 2) + varint(len(payload)) + payload


def patch_resource(data):
    changes = []

    def rewrite(payload, depth=0):
        try:
            records = list(fields(payload))
        except ValueError:
            return payload
        if depth > 20:
            return payload
        if any(number == 1 and wire == 0 and value == 27224 for number, wire, value, _ in records):
            if changes:
                raise ValueError('More than one external-devices list found')
            row_groups = [(i, value) for i, (number, wire, value, _) in enumerate(records)
                          if number == 9 and wire == 2]
            if len(row_groups) != 1:
                raise ValueError('Unexpected external-devices row group')
            group_index, group = row_groups[0]
            rows = list(fields(group))
            identities = []
            template = None
            for number, wire, value, raw in rows:
                if number == 1 and wire == 2:
                    row_fields = list(fields(value))
                    identifier = next((v for n, w, v, _ in row_fields if n == 1 and w == 0), None)
                    identities.append(identifier)
                    if identifier == 1:
                        template = row_fields
            if identities != [1, 2, 4, 11, 5] or template is None:
                raise ValueError('Unexpected original external-devices row identities')
            appended = bytearray(group)
            for identifier, title in [(12, 'Android Auto'), (13, 'CarPlay')]:
                new_row = b''.join(
                    varint(8) + varint(identifier) if number == 1 and wire == 0 else raw
                    for number, wire, value, raw in template if number != 3)
                # No feature ID is imposed on the added rows. Native hooks assign
                # literal labels and enable them through the original list API.
                appended.extend(message_field(1, new_row))
                changes.append({'item_id': identifier, 'label_assigned_by_native_hook': title,
                                'template_item_id': 1, 'feature_gate_removed': True})
            result = b''.join(message_field(9, bytes(appended)) if i == group_index else raw
                              for i, (_, _, _, raw) in enumerate(records))
            # All original row bytes remain exactly the prefix of the new group.
            assert bytes(appended).startswith(group)
            return result
        output = bytearray()
        for number, wire, value, raw in records:
            if wire == 2:
                rewritten = rewrite(value, depth+1)
                output.extend(message_field(number, rewritten) if rewritten != value else raw)
            else:
                output.extend(raw)
        return bytes(output)

    result = rewrite(data)
    if len(changes) != 2:
        raise ValueError('Original external-devices list was not found exactly once')
    return result, changes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    if args.input:
        if args.input.resolve() == args.output.resolve():
            parser.error('Output must be separate from the original resource')
        original = args.input.read_bytes()
        source = str(args.input)
    else:
        inventory = json.loads((args.root / 'outputs/native-integration/ifs-inventory.json').read_text())
        entry = next(x for x in inventory['imagefs']['entries']
                     if x.get('path') == 'opt/hmi/data/ro/app/hmimultimedia/hmimultimedia.pba')
        with Path(inventory['source']).open('rb') as stream:
            stream.seek(entry['absolute_offset'])
            original = stream.read(entry['size'])
        source = inventory['source'] + ':' + entry['path']
    patched, changes = patch_resource(original)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(patched)
    manifest = {'source': source, 'original_sha256': hashlib.sha256(original).hexdigest(),
                'output': str(args.output), 'sha256': hashlib.sha256(patched).hexdigest(),
                'original_bytes': len(original), 'patched_bytes': len(patched),
                'component_id': 27224, 'appended_rows': changes,
                'requires': 'Experimental native_devices.c label and selection hooks',
                'runtime_verified': False}
    args.output.with_suffix(args.output.suffix + '.manifest.json').write_text(
        json.dumps(manifest, indent=2), encoding='utf-8')
    print(json.dumps(manifest))


if __name__ == '__main__':
    main()
