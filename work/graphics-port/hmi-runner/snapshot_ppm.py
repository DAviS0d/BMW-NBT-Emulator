# © 2026 davisod & JEtsKi
"""Lossless RGB format conversion of an actual renderer framebuffer."""
import argparse
import struct
import zlib
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('source', type=Path)
parser.add_argument('destination', type=Path)
args = parser.parse_args()
raw = args.source.read_bytes()
magic, dimensions, maximum, pixels = raw.split(b'\n', 3)
assert magic == b'P6' and maximum == b'255'
width, height = map(int, dimensions.split())
assert len(pixels) == width * height * 3

def chunk(kind, body):
    return struct.pack('>I', len(body)) + kind + body + struct.pack('>I', zlib.crc32(kind + body) & 0xffffffff)

rows = b''.join(b'\0' + pixels[y * width * 3:(y + 1) * width * 3] for y in range(height))
png = (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0))
       + chunk(b'IDAT', zlib.compress(rows)) + chunk(b'IEND', b''))
args.destination.parent.mkdir(parents=True, exist_ok=True)
args.destination.write_bytes(png)
print(args.destination.resolve())
print('RGB bytes:', len(pixels), 'nonzero bytes:', len(pixels) - pixels.count(0))
