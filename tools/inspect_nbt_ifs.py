"""Read-only QNX imagefs inventory and explicitly selected file extraction.

Directory layout reference: OpenQNX sys/image.h (32-bit QNX image structures),
https://raw.githubusercontent.com/vocho/openqnx/master/trunk/services/system/public/sys/image.h
No guest file or executable is run or patched by this tool.
"""
import argparse
import hashlib
import json
import mmap
import re
import stat
import struct
from pathlib import Path, PurePosixPath

REFERENCE = 'https://raw.githubusercontent.com/vocho/openqnx/master/trunk/services/system/public/sys/image.h'
DEFAULT_PATTERNS = r'sport|torque|power|vehicle|engine|speed|rpm|bluetooth|external|carplay|android|navigation|navi|gps|position'


def sha256_file(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def bounded(data, offset, size, limit=None):
    limit = len(data) if limit is None else limit
    if offset < 0 or size < 0 or offset + size > limit:
        raise ValueError(f'Out-of-bounds range: offset={offset} size={size} limit={limit}')
    return data[offset:offset + size]


def cstring(data, start, end):
    bounded(data, start, end - start)
    terminator = data.find(b'\0', start, end)
    if terminator < 0:
        raise ValueError(f'Unterminated path/string at {start}')
    return data[start:terminator].decode('utf-8', errors='replace')


def parse_imagefs(data, offset):
    bounded(data, offset, 89)
    if data[offset:offset + 7] != b'imagefs':
        raise ValueError('No imagefs signature at selected offset')
    flags = data[offset + 7]
    endian = '>' if flags & 1 else '<'
    image_size, hdr_dir_size, dir_offset = struct.unpack_from(endian + '3I', data, offset + 8)
    if not 89 <= dir_offset < hdr_dir_size <= image_size or offset + image_size > len(data):
        raise ValueError('Invalid imagefs header bounds')
    directory_end = offset + hdr_dir_size
    position = offset + dir_offset
    entries = []
    while position + 2 <= directory_end:
        size = struct.unpack_from(endian + 'H', data, position)[0]
        if size == 0:
            break
        if size < 24 or size % 4 or position + size > directory_end:
            raise ValueError(f'Invalid directory entry at {position}')
        size, extattr, inode, mode, gid, uid, mtime = struct.unpack_from(endian + 'HH5I', data, position)
        entry = {'dirent_offset': position, 'dirent_size': size, 'inode': inode,
                 'mode': oct(mode), 'gid': gid, 'uid': uid, 'mtime': mtime}
        kind = stat.S_IFMT(mode)
        if kind == stat.S_IFREG:
            if size < 36:
                raise ValueError('Truncated regular file entry')
            file_offset, file_size = struct.unpack_from(endian + '2I', data, position + 24)
            bounded(data, offset + file_offset, file_size, offset + image_size)
            entry.update(type='file', image_offset=file_offset, absolute_offset=offset + file_offset, size=file_size)
            path_start = position + 32
        elif kind == stat.S_IFLNK:
            if size < 32:
                raise ValueError('Truncated symlink entry')
            sym_offset, sym_size = struct.unpack_from(endian + '2H', data, position + 24)
            bounded(data, position + sym_offset, sym_size, position + size)
            entry.update(type='symlink', target=bounded(data, position + sym_offset, sym_size).rstrip(b'\0').decode('utf-8', errors='replace'))
            path_start = position + 28
        elif kind == stat.S_IFDIR:
            entry['type'] = 'directory'
            path_start = position + 24
        else:
            entry['type'] = 'special'
            path_start = position + 32
        entry['path'] = cstring(data, path_start, position + (extattr or size))
        if inode:
            entries.append(entry)
        position += size
    if not entries:
        raise ValueError('Imagefs directory contains no entries')
    return {'header_offset': offset, 'flags': flags, 'endian': 'big' if flags & 1 else 'little',
            'image_size': image_size, 'hdr_dir_size': hdr_dir_size, 'dir_offset': dir_offset,
            'mountpoint': cstring(data, offset + 88, offset + dir_offset), 'entries': entries}


def find_imagefs(data, offset=None):
    if offset is not None:
        return parse_imagefs(data, offset)
    position = 0
    candidates = []
    while True:
        position = data.find(b'imagefs', position)
        if position < 0:
            break
        try:
            candidates.append(parse_imagefs(data, position))
        except (ValueError, struct.error):
            pass
        position += 7
    if len(candidates) != 1:
        raise ValueError(f'Expected one valid imagefs, found {len(candidates)}; select --header-offset explicitly')
    return candidates[0]


def elf_symbols(data, pattern=DEFAULT_PATTERNS):
    """Inspect dynamic symbol tables in ELF32 only; no disassembly or execution."""
    if data[:4] != b'\x7fELF' or data[4] != 1 or data[5] not in (1, 2):
        raise ValueError('Expected ELF32 with supported byte order')
    endian = '<' if data[5] == 1 else '>'
    bounded(data, 0, 52)
    machine = struct.unpack_from(endian + 'H', data, 18)[0]
    phoff, shoff = struct.unpack_from(endian + '2I', data, 28)
    phentsize, phnum, shentsize, shnum, shstrndx = struct.unpack_from(endian + '5H', data, 42)
    if shentsize < 40 or phentsize < 32:
        raise ValueError('Unsupported ELF header entry size')
    bounded(data, shoff, shnum * shentsize)
    bounded(data, phoff, phnum * phentsize)
    sections = [struct.unpack_from(endian + '10I', data, shoff + i * shentsize) for i in range(shnum)]
    loads = []
    for i in range(phnum):
        kind, offset, virtual, physical, filesz, memsz, flags, align = struct.unpack_from(endian + '8I', data, phoff + i * phentsize)
        if kind == 1:
            bounded(data, offset, filesz)
            loads.append((virtual, offset, filesz))
    def file_offset(address):
        return next((offset + address - virtual for virtual, offset, size in loads if virtual <= address < virtual + size), None)
    symbols = []
    for section in sections:
        name, kind, flags, address, offset, size, link, info, align, entsize = section
        if kind != 11:
            continue
        if entsize < 16 or size % entsize or link >= shnum:
            raise ValueError('Invalid dynamic symbol section')
        bounded(data, offset, size)
        strings = sections[link]
        str_offset, str_size = strings[4:6]
        bounded(data, str_offset, str_size)
        for position in range(offset, offset + size, entsize):
            st_name, value, symbol_size, st_info, other, index = struct.unpack_from(endian + '3IBBH', data, position)
            if st_name >= str_size:
                raise ValueError('Dynamic symbol string outside linked string table')
            name = cstring(data, str_offset + st_name, str_offset + str_size)
            if not name:
                continue
            symbols.append({'name': name, 'value': hex(value), 'size': symbol_size,
                            'defined': index != 0, 'type': st_info & 15,
                            'binding': st_info >> 4, 'file_offset': file_offset(value) if index else None,
                            'symbol_record_offset': position})
    regex = re.compile(pattern, re.IGNORECASE)
    matching = [symbol for symbol in symbols if regex.search(symbol['name'])]
    topics = {
        'sports_vehicle': r'SportInstrument|SportDisplay|Torque|EnginePower|EngineSpeed|CPxyVehicle$',
        'external_devices': r'ExternalDevice|CarPlay|AndroidAuto',
        'bluetooth': r'^CPxyBluetooth$|CDevExternalBluetooth|BluetoothService|A2DPStatus',
        'navigation': r'^CPxyMapControl$|^CPxyNavigationInfo$|CJNaviMapMapController|MapEngine|NavigationServer',
    }
    candidates = {topic: [] for topic in topics}
    for match in re.finditer(rb'[ -~]{6,}', data):
        text = match.group().decode('ascii')
        for topic, expression in topics.items():
            if re.search(expression, text, re.IGNORECASE):
                address = next((virtual + match.start() - offset for virtual, offset, size in loads
                                if offset <= match.start() < offset + size), None)
                candidates[topic].append({'text': text, 'file_offset': match.start(),
                                          'virtual_address': hex(address) if address is not None else None})
    return {'format': 'ELF32', 'machine': machine, 'dynamic_symbol_count': len(symbols),
            'defined_symbol_count': sum(s['defined'] for s in symbols),
            'pattern': pattern, 'matching_symbols': matching,
            'candidate_strings': candidates,
            'limits': 'Dynamic symbols and string locations only. Names suggest candidate interfaces; no function semantics or runtime behavior verified. Absence in dynamic symbols does not prove absent internal code.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--header-offset', type=lambda s: int(s, 0))
    parser.add_argument('--extract', action='append', default=[], metavar='IMAGE_PATH', help='Exact image path to extract; repeatable')
    parser.add_argument('--output-dir', type=Path, help='Required when extracting')
    parser.add_argument('--report', type=Path, help='Save complete inventory as JSON')
    parser.add_argument('--elf-symbols', action='store_true', help='Inventory selected ELF32 dynamic symbols')
    parser.add_argument('--pattern', default=DEFAULT_PATTERNS)
    args = parser.parse_args()
    if args.extract and not args.output_dir:
        parser.error('--extract requires --output-dir')
    source = args.source.resolve(strict=True)
    with source.open('rb') as stream, mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as data:
        inventory = find_imagefs(data, args.header_offset)
        report = {'source': str(source), 'source_size': len(data), 'source_sha256': sha256_file(source),
                  'layout_reference': REFERENCE, 'imagefs': inventory, 'extracted': []}
        for requested in args.extract:
            image_path = PurePosixPath(requested)
            if image_path.is_absolute() or '..' in image_path.parts or '\\' in requested or ':' in requested:
                parser.error('Extraction path must be a relative image path without traversal')
            matches = [entry for entry in inventory['entries'] if entry['path'] == requested and entry['type'] == 'file']
            if len(matches) != 1:
                parser.error(f'Expected one regular file for {requested!r}; found {len(matches)}')
            entry = matches[0]
            output = args.output_dir.resolve() / Path(*image_path.parts)
            if not output.resolve().is_relative_to(args.output_dir.resolve()):
                parser.error('Extraction path escapes output directory')
            if output.exists():
                parser.error(f'Output already exists; select a new output directory: {output}')
            payload = bounded(data, entry['absolute_offset'], entry['size'])
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(payload)
            record = {**entry, 'output': str(output), 'sha256': hashlib.sha256(payload).hexdigest()}
            if args.elf_symbols and payload[:4] == b'\x7fELF':
                record['elf'] = elf_symbols(payload, args.pattern)
            report['extracted'].append(record)
    serialized = json.dumps(report, indent=2)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(serialized + '\n', encoding='utf-8')
        print(json.dumps({'report': str(args.report.resolve()), 'source_sha256': report['source_sha256'],
                          'header_offset': inventory['header_offset'], 'entry_count': len(inventory['entries']),
                          'extracted': [{k: v for k, v in item.items() if k != 'elf'} for item in report['extracted']]}, indent=2))
    else:
        print(serialized)


if __name__ == '__main__':
    main()
