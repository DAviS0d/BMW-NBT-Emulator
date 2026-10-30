# © 2026 davisod & JEtsKi
"""Decoder for the EVA startup animations (eva_ani_*.pdds) -> PNG frames.

Format, established from the files themselves (docs/RAPORT_STARTUP_M.md):
  'PDDS' + 124-byte DDS header (NVTT, FourCC DXT1, width, height,
  mipMapCount = frame count), then one chunk per frame:
  'HEAD' u32 length, payload = LZO1X stream of the frame's DXT1 blocks.
Usage:
  py -3 pdds.py FILE.pdds OUTDIR        (writes frame_000.png ...)
Output PNGs are derived from firmware and stay out of git.
"""
import struct
import sys
import zlib
from pathlib import Path


def lzo1x(src, dictionary=b"", limit=1 << 24):
    """LZO1X decompression (algorithm of minilzo lzo1x_d). `dictionary` is
    prefixed output that back-references may reach (not returned)."""
    out = bytearray(dictionary)
    base = len(out)
    ip = 0

    def copy_match(pos, count):
        if pos < 0:
            raise ValueError(f"match before start ({pos})")
        for _ in range(count):
            out.append(out[pos])
            pos += 1

    def long_length(t, bias):
        nonlocal ip
        if t == 0:
            while src[ip] == 0:
                t += 255
                ip += 1
            t += bias + src[ip]
            ip += 1
        return t

    state = "first"
    t = 0
    if src[0] > 17:
        t = src[0] - 17
        ip = 1
        if t < 4:
            state = "match_next"
        else:
            out += src[ip:ip + t]
            ip += t
            state = "first_literal_run"
    while True:
        if len(out) - base > limit:
            raise ValueError("output too long")
        if state == "first":
            state = "loop"
        if state == "loop":
            t = src[ip]
            ip += 1
            if t >= 16:
                state = "match"
                continue
            t = long_length(t, 15)
            out += src[ip:ip + t + 3]
            ip += t + 3
            state = "first_literal_run"
        if state == "first_literal_run":
            t = src[ip]
            ip += 1
            if t >= 16:
                state = "match"
                continue
            pos = len(out) - (1 + 0x0800) - (t >> 2) - (src[ip] << 2)
            ip += 1
            copy_match(pos, 3)
            state = "match_done"
        if state == "match":
            if t >= 64:
                pos = len(out) - 1 - ((t >> 2) & 7) - (src[ip] << 3)
                ip += 1
                copy_match(pos, (t >> 5) - 1 + 2)
            elif t >= 32:
                t = long_length(t & 31, 31)
                pos = len(out) - 1 - ((src[ip] | src[ip + 1] << 8) >> 2)
                ip += 2
                copy_match(pos, t + 2)
            elif t >= 16:
                pos = len(out) - ((t & 8) << 11)
                t = long_length(t & 7, 7)
                pos -= (src[ip] | src[ip + 1] << 8) >> 2
                ip += 2
                if pos == len(out):
                    return bytes(out[base:])          # end of stream
                copy_match(pos - 0x4000, t + 2)
            else:
                pos = len(out) - 1 - (t >> 2) - (src[ip] << 2)
                ip += 1
                copy_match(pos, 2)
            state = "match_done"
        if state == "match_done":
            t = src[ip - 2] & 3
            if t == 0:
                state = "loop"
                continue
            state = "match_next"
        if state == "match_next":
            out += src[ip:ip + t]
            ip += t
            t = src[ip]
            ip += 1
            state = "match"


def read_pdds(path):
    data = Path(path).read_bytes()
    if data[:4] != b"PDDS" or data[0x54:0x58] != b"DXT1":
        raise ValueError("not a DXT1 PDDS file")
    height, width, linear, _, frames = struct.unpack_from("<5I", data, 12)
    chunks, offset = [], 0x80
    while offset + 8 <= len(data):
        tag, length = data[offset:offset + 4], struct.unpack_from("<I", data, offset + 4)[0]
        if tag != b"HEAD":
            raise ValueError(f"unexpected chunk {tag!r} at {offset:#x}")
        chunks.append(data[offset + 8:offset + 8 + length])
        offset += 8 + length
    return {"width": width, "height": height, "frame_bytes": linear, "frames": frames, "chunks": chunks}


def rgb565(c):
    return ((c >> 11) & 31) * 255 // 31, ((c >> 5) & 63) * 255 // 63, (c & 31) * 255 // 31


_BLOCK_CACHE = {}


def dxt1_block_rows(block):
    """Four 12-byte RGB rows of one DXT1 (BC1) block, cached by block bytes."""
    rows = _BLOCK_CACHE.get(block)
    if rows is None:
        c0, c1, bits = struct.unpack("<HHI", block)
        p0, p1 = rgb565(c0), rgb565(c1)
        if c0 > c1:
            palette = (p0, p1, tuple((2 * a + b) // 3 for a, b in zip(p0, p1)),
                       tuple((a + 2 * b) // 3 for a, b in zip(p0, p1)))
        else:
            palette = (p0, p1, tuple((a + b) // 2 for a, b in zip(p0, p1)), (0, 0, 0))
        palette = [bytes(c) for c in palette]
        rows = tuple(b"".join(palette[(bits >> (2 * (4 * y + x))) & 3] for x in range(4)) for y in range(4))
        if len(_BLOCK_CACHE) < 500000:
            _BLOCK_CACHE[block] = rows
    return rows


def dxt1_to_rgb(blocks, width, height):
    """Decode DXT1 blocks, row-major 4x4 tiles, to packed RGB."""
    rgb = bytearray(width * height * 3)
    bx = width // 4
    stride = width * 3
    for index in range(len(blocks) // 8):
        rows = dxt1_block_rows(blocks[index * 8:index * 8 + 8])
        at = (index // bx) * 4 * stride + (index % bx) * 12
        for y in range(4):
            rgb[at + y * stride:at + y * stride + 12] = rows[y]
    return bytes(rgb)


def write_png(path, rgb, width, height):
    rows = b"".join(b"\0" + rgb[y * width * 3:(y + 1) * width * 3] for y in range(height))
    chunk = lambda k, d: struct.pack(">I", len(d)) + k + d + struct.pack(">I", zlib.crc32(k + d) & 0xffffffff)
    Path(path).write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
                           + chunk(b"IDAT", zlib.compress(rows, 6)) + chunk(b"IEND", b""))


def apply_delta(previous, stream, blocks_x, blocks_y):
    """Inter frame: one code per DXT1 block, in row-major block order.
    0x00 + 8 bytes = new block; 0x80..0xff = copy the previous frame's block at
    (dx, dy) = ((code & 15) - 7, ((code >> 4) & 7) - 3); 0xb7 = unchanged."""
    out = bytearray(len(previous))
    pos = 0
    for index in range(blocks_x * blocks_y):
        code = stream[pos]
        if code == 0:
            out[index * 8:index * 8 + 8] = stream[pos + 1:pos + 9]
            pos += 9
            continue
        if code < 0x80:
            raise ValueError(f"unknown block code {code:#x} at block {index}")
        x = index % blocks_x + (code & 15) - 7
        y = index // blocks_x + ((code >> 4) & 7) - 3
        if not (0 <= x < blocks_x and 0 <= y < blocks_y):
            raise ValueError(f"reference outside frame at block {index}")
        source = (y * blocks_x + x) * 8
        out[index * 8:index * 8 + 8] = previous[source:source + 8]
        pos += 1
    if pos != len(stream):
        raise ValueError(f"delta stream has {len(stream) - pos} trailing bytes")
    return bytes(out)


def frames(path):
    """Yield (index, DXT1 bytes) for every frame: a key frame (raw DXT1 after
    LZO1X), then inter frames applied to the previous decoded frame."""
    info = read_pdds(path)
    blocks_x, blocks_y = info["width"] // 4, info["height"] // 4
    previous = None
    for index, chunk in enumerate(info["chunks"]):
        stream = lzo1x(chunk)
        if len(stream) == info["frame_bytes"] and (previous is None or stream.count(0xb7) < blocks_x * blocks_y // 2):
            blocks = stream
        elif previous is not None:
            blocks = apply_delta(previous, stream, blocks_x, blocks_y)
        else:
            raise ValueError("first frame is not a key frame")
        previous = blocks
        yield index, blocks


def main():
    source, destination = Path(sys.argv[1]), Path(sys.argv[2])
    destination.mkdir(parents=True, exist_ok=True)
    info = read_pdds(source)
    for index, blocks in frames(source):
        rgb = dxt1_to_rgb(blocks, info["width"], info["height"])
        write_png(destination / f"frame_{index:03d}.png", rgb, info["width"], info["height"])
        print(f"frame {index} ok", flush=True)


if __name__ == "__main__":
    main()
