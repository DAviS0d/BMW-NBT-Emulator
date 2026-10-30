"""Build a separate experimental, uncompressed x86 QNX IFS with file changes.

Original payload bytes are retained; replacements and additions are appended,
followed by a fresh directory/trailer. Existing dirent metadata is preserved.
Startup instructions are not modified. No default firmware is overwritten.

Layout references:
https://raw.githubusercontent.com/vocho/openqnx/master/trunk/services/system/public/sys/image.h
https://qnx.com/developers/docs/6.4.0/neutrino/building/load_process.html
The additive checksum convention is also checked against the input image.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import struct
import sys
import tempfile

from inspect_nbt_ifs import find_imagefs, parse_imagefs, sha256_file

LAYOUT_REFERENCE = 'https://raw.githubusercontent.com/vocho/openqnx/master/trunk/services/system/public/sys/image.h'
STARTUP_REFERENCE = 'https://qnx.com/developers/docs/6.4.0/neutrino/building/load_process.html'


def checksum32(data, start=0, end=None):
    end = len(data) if end is None else end
    if start < 0 or end < start or end > len(data) or (end - start) % 4:
        raise ValueError('Checksum region must be bounded and word aligned')
    view = memoryview(data)[start:end]
    if sys.byteorder == 'little':
        words = view.cast('I')
        try:
            return sum(words) & 0xffffffff
        finally:
            words.release()
            view.release()
    try:
        return sum(word[0] for word in struct.iter_unpack('<I', view)) & 0xffffffff
    finally:
        view.release()


def image_path(value):
    if not isinstance(value, str) or not value or '\\' in value or ':' in value or '\0' in value:
        raise ValueError('Image paths must be nonempty relative POSIX paths')
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in ('.', '..', '') for part in value.split('/')):
        raise ValueError(f'Unsafe image path: {value!r}')
    return path.as_posix()


def _record(path, inode, mode, file_offset=None, file_size=None):
    encoded = path.encode('utf-8') + b'\0'
    extra = struct.pack('<2I', file_offset, file_size) if file_offset is not None else b''
    size = (24 + len(extra) + len(encoded) + 3) & ~3
    if size > 65535:
        raise ValueError('Directory entry path is too long')
    return (struct.pack('<HH5I', size, 0, inode, mode, 0, 0, 0)
            + extra + encoded + b'\0' * (size - 24 - len(extra) - len(encoded)))


def repack(source, output, replacements=None, additions=None, *, add_mode=0o644):
    """Return a verified build manifest; reject input/output aliasing or overwrite.

    replacements/additions map relative image paths to host files. Replacements
    preserve mode/inode/owner/timestamp/extattrs, additions use root ownership,
    zero timestamps and monotonically assigned inodes. New parents are created.
    All new payloads are aligned to absolute 4 KiB boundaries for ELF mmap use.
    """
    source = Path(source).resolve(strict=True)
    output = Path(output).resolve()
    if source == output or output.exists():
        raise ValueError('Select a new output path; source/default images are never overwritten')
    replacements = {image_path(k): Path(v).resolve(strict=True) for k, v in (replacements or {}).items()}
    additions = {image_path(k): Path(v).resolve(strict=True) for k, v in (additions or {}).items()}
    if not replacements and not additions:
        raise ValueError('At least one replacement or addition is required')
    if replacements.keys() & additions.keys():
        raise ValueError('A path cannot be both a replacement and an addition')
    if type(add_mode) is not int or not 0 <= add_mode <= 0o777:
        raise ValueError('Added-file permissions must be in 0000..0777')
    original_hash = sha256_file(source)
    data = source.read_bytes()
    if data[:4] != b'\xeb\x7e\xff\0' or len(data) < 256:
        raise ValueError('Expected an x86 QNX startup header at offset zero')
    if data[6] & 0x1e or struct.unpack_from('<HH', data, 8) != (256, 3):
        raise ValueError('Only uncompressed little-endian x86 QNX images with 256-byte startup headers are supported')
    old_ram, startup_size, stored_size, fs_paddr, fs_size = struct.unpack_from('<5I', data, 28)
    inventory = find_imagefs(data)
    base = inventory['header_offset']
    old_end = base + inventory['image_size']
    if (base != startup_size or base % 4 or startup_size < 260
            or stored_size != old_end or fs_size != inventory['image_size']
            or inventory['endian'] != 'little' or old_ram < stored_size):
        raise ValueError('Unsupported startup/imagefs size or memory layout')
    if checksum32(data, 0, startup_size) or checksum32(data, base, old_end):
        raise ValueError('Input startup or imagefs additive checksum is invalid')
    entries = inventory['entries']
    by_path = {}
    for entry in entries:
        if entry['path'] in by_path:
            raise ValueError('Ambiguous duplicate directory path: ' + entry['path'])
        by_path[entry['path']] = entry
    for path in replacements:
        if path not in by_path or by_path[path]['type'] != 'file':
            raise ValueError('Replacement requires an existing regular image file: ' + path)
    for path in additions:
        if path in by_path:
            raise ValueError('Added path already exists: ' + path)

    # Retain everything before the old trailer, including original payloads and
    # directory. This also handles layouts with payloads after their directory.
    built = bytearray(data[:old_end - 4])
    payload_records = []
    offsets = {}
    for path in sorted({**replacements, **additions}):
        host = replacements.get(path, additions.get(path))
        payload = host.read_bytes()
        padding = (-len(built)) % 4096
        built.extend(b'\0' * padding)
        offsets[path] = (len(built) - base, len(payload))
        built.extend(payload)
        old = by_path.get(path)
        payload_records.append({
            'path': path, 'operation': 'replace' if old else 'add',
            'host_source': str(host), 'size': len(payload),
            'image_offset': offsets[path][0], 'absolute_offset': offsets[path][0] + base,
            'sha256': hashlib.sha256(payload).hexdigest(),
            'original_size': old['size'] if old else None,
            'original_sha256': hashlib.sha256(data[old['absolute_offset']:old['absolute_offset'] + old['size']]).hexdigest() if old else None,
        })
    built.extend(b'\0' * ((-len(built)) % 4))
    new_dir_start = len(built)
    raw_directory = data[base + inventory['dir_offset']:base + inventory['hdr_dir_size']]
    cursor = 0
    while cursor + 2 <= len(raw_directory):
        size = struct.unpack_from('<H', raw_directory, cursor)[0]
        if size == 0:
            break
        if size < 24 or size % 4 or cursor + size > len(raw_directory):
            raise ValueError('Invalid original directory record')
        record = bytearray(raw_directory[cursor:cursor + size])
        absolute_record = base + inventory['dir_offset'] + cursor
        entry = next((e for e in entries if e['dirent_offset'] == absolute_record), None)
        if entry is not None and entry['path'] in replacements:
            struct.pack_into('<2I', record, 24, *offsets[entry['path']])
        built.extend(record)
        cursor += size
    next_inode = max((e['inode'] & 0x1fffffff for e in entries), default=0) + 1
    directories = {e['path'] for e in entries if e['type'] == 'directory'}
    new_directories = set()
    for path in additions:
        for parent in PurePosixPath(path).parents:
            name = '' if str(parent) == '.' else str(parent)
            if name in by_path and by_path[name]['type'] != 'directory':
                raise ValueError('New file parent is not a directory: ' + name)
            if name and name not in directories:
                new_directories.add(name)
    for path in sorted(new_directories, key=lambda p: (len(PurePosixPath(p).parts), p)):
        if next_inode >= 0x20000000:
            raise ValueError('Inode number exceeds the regular inode range')
        built.extend(_record(path, next_inode, stat.S_IFDIR | 0o755))
        next_inode += 1
    for path in sorted(additions):
        if next_inode >= 0x20000000:
            raise ValueError('Inode number exceeds the regular inode range')
        built.extend(_record(path, next_inode, stat.S_IFREG | add_mode, *offsets[path]))
        next_inode += 1
    # Fresh zero-size directory terminator followed by one checksum word.
    built.extend(b'\0' * 4)
    new_hdr_dir_size = len(built) - base
    new_fs_size = new_hdr_dir_size + 4
    new_stored_size = base + new_fs_size
    new_ram_size = old_ram + new_stored_size - stored_size
    if max(new_fs_size, new_stored_size, new_ram_size) > 0xffffffff:
        raise ValueError('Repacked image exceeds 32-bit startup size fields')
    struct.pack_into('<3I', built, base + 8, new_fs_size, new_hdr_dir_size, new_dir_start - base)
    struct.pack_into('<I', built, 28, new_ram_size)
    struct.pack_into('<I', built, 36, new_stored_size)
    struct.pack_into('<I', built, 44, new_fs_size)
    struct.pack_into('<I', built, startup_size - 4, 0)
    struct.pack_into('<I', built, startup_size - 4, (-checksum32(built, 0, startup_size)) & 0xffffffff)
    built.extend(struct.pack('<I', (-checksum32(built, base, len(built))) & 0xffffffff))
    built.extend(data[old_end:])
    updated = parse_imagefs(built, base)
    updated_paths = {e['path']: e for e in updated['entries']}
    for record in payload_records:
        entry = updated_paths[record['path']]
        actual_hash = hashlib.sha256(memoryview(built)[entry['absolute_offset']:entry['absolute_offset'] + entry['size']]).hexdigest()
        if actual_hash != record['sha256'] or entry['size'] != record['size']:
            raise ValueError('Repacked file failed extraction verification: ' + record['path'])
    for entry in entries:
        if entry['type'] == 'file' and entry['path'] not in replacements:
            copied = updated_paths[entry['path']]
            if copied['absolute_offset'] != entry['absolute_offset'] or copied['size'] != entry['size']:
                raise ValueError('Untouched file offset or size changed: ' + entry['path'])
    startup_preserved = built[256:startup_size - 4] == data[256:startup_size - 4]
    if not startup_preserved or checksum32(built, 0, startup_size) or checksum32(built, base, new_stored_size):
        raise ValueError('Startup preservation or output checksum verification failed')
    if sha256_file(source) != original_hash:
        raise ValueError('Source image changed during repacking')
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(prefix=output.name + '.', suffix='.tmp',
                                         dir=output.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(built)
            stream.flush()
            os.fsync(stream.fileno())
        # Hard-link creation is atomic and refuses concurrent output overwrite.
        os.link(temporary, output)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return {
        'type': 'EXPERIMENTAL_REPACKED_QNX_IFS', 'source': str(source),
        'source_sha256': original_hash, 'output': str(output),
        'output_sha256': hashlib.sha256(built).hexdigest(),
        'source_size': len(data), 'output_size': len(built),
        'startup_size': startup_size, 'startup_instructions_preserved': startup_preserved,
        'startup_checksum_valid': True, 'imagefs_checksum_valid': True,
        'imagefs_header_offset': base, 'imagefs_size': new_fs_size,
        'stored_size': new_stored_size, 'ram_size': new_ram_size,
        'directory_offset': updated['dir_offset'], 'entry_count': len(updated['entries']),
        'files': payload_records, 'added_directories': sorted(new_directories),
        'trailing_bytes_preserved': len(data) - old_end,
        'references': [LAYOUT_REFERENCE, STARTUP_REFERENCE],
        'runtime_boot_verified': False,
    }


def parse_specs(values):
    result = {}
    for value in values:
        path, separator, host = value.partition('=')
        if not separator or not host:
            raise ValueError('File specifications must be IMAGE_PATH=HOST_FILE')
        path = image_path(path)
        if path in result:
            raise ValueError('Repeated file specification: ' + path)
        result[path] = Path(host)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('source', type=Path)
    parser.add_argument('--output', type=Path, required=True, help='new experimental .ifs path')
    parser.add_argument('--replace', action='append', default=[], metavar='IMAGE_PATH=HOST_FILE')
    parser.add_argument('--add', action='append', default=[], metavar='IMAGE_PATH=HOST_FILE')
    parser.add_argument('--add-mode', type=lambda s: int(s, 8), default=0o644, metavar='OCTAL')
    parser.add_argument('--report', type=Path, help='new JSON build manifest path')
    args = parser.parse_args(argv)
    try:
        if args.report and (args.report.exists() or args.report.resolve() in (args.source.resolve(), args.output.resolve())):
            raise ValueError('Select a new report path separate from source and output')
        result = repack(args.source, args.output, parse_specs(args.replace), parse_specs(args.add), add_mode=args.add_mode)
        serialized = json.dumps(result, indent=2) + '\n'
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            with args.report.open('x', encoding='utf-8') as stream:
                stream.write(serialized)
        print(serialized, end='')
        return 0
    except (OSError, ValueError) as error:
        parser.exit(1, f'Repack failed: {error}\n')


if __name__ == '__main__':
    raise SystemExit(main())
