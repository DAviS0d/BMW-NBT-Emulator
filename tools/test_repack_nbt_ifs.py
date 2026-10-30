"""Small synthetic IFS roundtrips; no proprietary firmware needed."""
import hashlib
from pathlib import Path
import stat
import struct
import tempfile
import unittest

from inspect_nbt_ifs import find_imagefs
from repack_nbt_ifs import _record, checksum32, repack


def fixture():
    startup = 512
    data = bytearray(4096)
    data[256:startup - 4] = bytes(range(252))
    data[:4] = b'\xeb\x7e\xff\0'
    struct.pack_into('<HH', data, 8, 256, 3)
    data[startup:startup + 8] = b'imagefs\x04'
    data[startup + 88:startup + 90] = b'/\0'
    files = {'boot/lib/first.so': b'original first', 'boot/keep.bin': b'UNCHANGED\0\xff'}
    offsets = {}
    for path, content in files.items():
        data.extend(b'\0' * ((-len(data)) % 4096))
        offsets[path] = (len(data) - startup, len(content))
        data.extend(content)
    data.extend(b'\0' * ((-len(data)) % 4))
    directory = len(data)
    for inode, path in enumerate(('', 'boot', 'boot/lib'), 1):
        data.extend(_record(path, inode, stat.S_IFDIR | 0o755))
    for inode, path in enumerate(files, 4):
        data.extend(_record(path, inode, stat.S_IFREG | 0o755, *offsets[path]))
    data.extend(b'\0' * 4)
    fs_size = len(data) + 4 - startup
    struct.pack_into('<3I', data, startup + 8, fs_size, fs_size - 4, directory - startup)
    struct.pack_into('<5I', data, 28, startup + fs_size, startup, startup + fs_size, 0, fs_size)
    struct.pack_into('<I', data, startup - 4, (-checksum32(data, 0, startup)) & 0xffffffff)
    data.extend(struct.pack('<I', (-checksum32(data, startup, len(data))) & 0xffffffff))
    data.extend(b'\0' * 4)
    return data, files


class RepackTests(unittest.TestCase):
    def test_replacement_and_addition_roundtrip_is_deterministic_and_preserves_source(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            original, files = fixture()
            source = root / 'source.ifs'
            source.write_bytes(original)
            replacement = root / 'larger.so'
            replacement.write_bytes(bytes(range(256)) * 20)
            addition = root / 'resource.xml'
            addition.write_bytes(b'<pluginApp/>')
            args = ({'boot/lib/first.so': replacement}, {'opt/test/new.xml': addition})
            first = repack(source, root / 'one.ifs', *args)
            second = repack(source, root / 'two.ifs', *args)
            self.assertEqual(first['output_sha256'], second['output_sha256'])
            self.assertEqual(source.read_bytes(), original)
            data = (root / 'one.ifs').read_bytes()
            self.assertEqual(data[256:508], original[256:508])
            self.assertEqual(checksum32(data, 0, 512), 0)
            inventory = find_imagefs(data)
            self.assertEqual(checksum32(data, 512, 512 + inventory['image_size']), 0)
            entries = {e['path']: e for e in inventory['entries']}
            for path, content in {'boot/lib/first.so': replacement.read_bytes(),
                                  'opt/test/new.xml': addition.read_bytes(),
                                  'boot/keep.bin': files['boot/keep.bin']}.items():
                entry = entries[path]
                self.assertEqual(data[entry['absolute_offset']:entry['absolute_offset'] + entry['size']], content)
            self.assertEqual(entries['boot/lib/first.so']['inode'], 4)
            self.assertEqual(entries['boot/lib/first.so']['mode'], oct(stat.S_IFREG | 0o755))
            self.assertEqual(entries['opt']['type'], 'directory')
            self.assertEqual(entries['opt/test']['type'], 'directory')
            self.assertTrue(first['startup_instructions_preserved'])

    def test_rejects_overwrite_bad_paths_and_invalid_input_checksums(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            original, _ = fixture()
            source = root / 'source.ifs'
            source.write_bytes(original)
            payload = root / 'payload'
            payload.write_bytes(b'x')
            for target, replacements, additions in (
                (source, {'boot/lib/first.so': payload}, {}),
                (root / 'bad.ifs', {'../file': payload}, {}),
                (root / 'bad.ifs', {'missing': payload}, {}),
                (root / 'bad.ifs', {}, {'boot/keep.bin': payload}),
                (root / 'bad.ifs', {}, {'boot/keep.bin/child': payload}),
            ):
                with self.assertRaises(ValueError):
                    repack(source, target, replacements, additions)
                self.assertEqual(source.read_bytes(), original)
            original[300] ^= 1
            source.write_bytes(original)
            with self.assertRaises(ValueError):
                repack(source, root / 'bad.ifs', {'boot/lib/first.so': payload})


if __name__ == '__main__':
    unittest.main()
