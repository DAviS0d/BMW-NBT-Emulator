import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / 'tools'))
from patch_external_devices import fields, message_field, patch_resource, varint


def original_fixture():
    rows = []
    for identity in [1, 2, 4, 11, 5]:
        # Distinct unknown fields deliberately exercise byte preservation.
        row = (varint(8) + varint(identity) + varint(16) + varint(1180 + identity)
               + varint(24) + varint(20068) + message_field(4, b'opaque label'))
        rows.append(message_field(1, row))
    component = varint(8) + varint(27224) + message_field(2, b'defaultList') + message_field(9, b''.join(rows))
    return message_field(2, message_field(8, component)), b''.join(rows)


def find_component(data):
    for number, wire, value, raw in fields(data):
        if number == 8 and wire == 2:
            return value
        if wire == 2:
            try:
                result = find_component(value)
                if result:
                    return result
            except ValueError:
                pass


class ExternalDevicePatchTests(unittest.TestCase):
    def test_preserves_original_row_bytes_and_appends_ids(self):
        original, original_rows = original_fixture()
        output, changes = patch_resource(original)
        component = find_component(output)
        group = next(value for number, wire, value, _ in fields(component) if number == 9)
        self.assertTrue(group.startswith(original_rows))
        rows = [value for number, wire, value, _ in fields(group) if number == 1]
        identities = [next(value for number, wire, value, _ in fields(row) if number == 1) for row in rows]
        self.assertEqual(identities, [1, 2, 4, 11, 5, 12, 13])
        for row in rows[-2:]:
            self.assertNotIn(3, [number for number, _, _, _ in fields(row)])
        self.assertEqual([x['label_assigned_by_native_hook'] for x in changes], ['Android Auto', 'CarPlay'])

    def test_already_patched_resource_is_rejected(self):
        output, _ = patch_resource(original_fixture()[0])
        with self.assertRaises(ValueError):
            patch_resource(output)

    def test_unrecognized_resource_is_rejected(self):
        with self.assertRaises(ValueError):
            patch_resource(message_field(1, b'not the multimedia resource'))


if __name__ == '__main__':
    unittest.main()
