# © 2026 davisod & JEtsKi
"""Startup screen selection from the user's own coding (EVA emulation for the viewer).

On the car, EVA (NBTCarHUOne, CPEarlyVideoControlDevImpl) shows the startup
screen chosen by coding: STARTUP_TYPE black/splash/animation, STARTUP_EMBLEM
variant. The emulator does not run EVA, so the viewer reproduces its choice
with the original firmware resources (docs/RAPORT_STARTUP_M.md).

Values are read from the NCD (NBT_NCD, default as in read_ncd_input.py), at
the bit positions of the descriptors compiled into HmiMain3D
(syset-native/hmi_native_coding_schema.json). Nothing is hardcoded per car.
"""
import json
import os
import struct
import sys
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[2]


def _default_ncd():
    """NBT_NCD, else the CAFD 00000DED coding shipped in <workspace>/coding/, else C:\\Data."""
    if os.environ.get("NBT_NCD"):
        return Path(os.environ["NBT_NCD"])
    bundled = sorted((WORKSPACE / "coding").glob("CAFD_00000DED_*.ncd"))
    return bundled[-1] if bundled else Path(r"C:\Data\CAF\CAFD_00000DED_003_012_025.ncd")


NCD = _default_ncd()
SCHEMA = WORKSPACE / "work/graphics-port/syset-native/hmi_native_coding_schema.json"
FRAMES = Path(__file__).resolve().parent / "frames"
TYPES = {0: "black", 1: "splash", 2: "animation"}
SRECORD_ADDRESS_BYTES = {"1": 2, "2": 3, "3": 4}


def read_ncd(path):
    """Coding memory {address: byte} from Motorola S-records, checksums verified."""
    memory = {}
    for number, line in enumerate(path.read_text(encoding="ascii").splitlines(), 1):
        line = line.strip()
        if not line or line[1] not in SRECORD_ADDRESS_BYTES:
            continue
        raw = bytes.fromhex(line[2:])
        if len(raw) != raw[0] + 1 or sum(raw) & 255 != 255:
            raise ValueError(f"S-record checksum/count error at line {number}")
        width = SRECORD_ADDRESS_BYTES[line[1]]
        address = int.from_bytes(raw[1:1 + width], "big")
        for index, byte in enumerate(raw[1 + width:-1]):
            memory[address + index] = byte
    return memory


def coded_value(memory, records, parameter):
    """Field value of a coding parameter at its HMI descriptor position."""
    record = next(r for r in records if r["parameter"] == parameter)
    address = (int(record["block_id"], 16) << 8) + record["first_byte"]
    mask = record["mask"]
    return (memory[address] & mask) >> ((mask & -mask).bit_length() - 1)


def eva_images():
    override = os.environ.get("NBT_EVA_IMAGES")
    if override:
        return Path(override)
    found = sorted(WORKSPACE.glob("outputs/NBT_files/*/Intel/fs/sda0/repository/istep/opt/car/data/eva/images"))
    return found[0] if found else None


def png_size(path):
    data = path.read_bytes()[:24]
    return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")


def startup_screen(width=1280, height=480):
    """{'type', 'emblem', 'splash', 'frames', ...} for the viewer, or {'error'}."""
    try:
        records = json.loads(SCHEMA.read_text())["records"]
        memory = read_ncd(NCD)
        kind = TYPES.get(coded_value(memory, records, "STARTUP_TYPE"), "black")
        emblem = coded_value(memory, records, "STARTUP_EMBLEM")
    except (OSError, ValueError, KeyError, StopIteration) as error:
        return {"error": f"coding unavailable: {error!r}", "ncd": str(NCD)}
    result = {"type": kind, "emblem": emblem, "ncd": str(NCD), "splash": None, "frames": []}
    images = eva_images()
    if images is None:
        result["error"] = "EVA images not found in outputs/NBT_files"
        return result
    # EVA keeps one file per display size (07 = 800x480, 10 = 1280x480).
    for candidate in sorted(images.glob(f"eva_splash_0x{emblem:02X}_*.png")):
        if png_size(candidate) == (width, height):
            result["splash"] = str(candidate)
    if kind == "animation":
        for candidate in sorted(images.glob(f"eva_ani_0x{emblem:02X}_*.pdds")):
            header = candidate.read_bytes()[:20]
            if header[:4] == b"PDDS" and struct.unpack_from("<II", header, 12) == (height, width):
                result["animation_source"] = str(candidate)
        animation = FRAMES / f"eva_ani_0x{emblem:02X}"
        if animation.is_dir():
            result["frames"] = [str(p) for p in sorted(animation.glob("frame_*.png"))]
    return result


def prepare_frames(choice):
    """Decode the coded animation into frames/eva_ani_0x<emblem>/ (once).
    Written to a temporary folder and renamed, so a partial decode is never used."""
    source = choice.get("animation_source")
    if not source or choice.get("frames"):
        return False
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import pdds
    target = FRAMES / f"eva_ani_0x{choice['emblem']:02X}"
    temporary = target.with_name(target.name + ".tmp")
    temporary.mkdir(parents=True, exist_ok=True)
    info = pdds.read_pdds(source)
    for index, blocks in pdds.frames(source):
        rgb = pdds.dxt1_to_rgb(blocks, info["width"], info["height"])
        pdds.write_png(temporary / f"frame_{index:03d}.png", rgb, info["width"], info["height"])
    temporary.rename(target)
    return True


if __name__ == "__main__":
    selected = startup_screen()
    if "--prepare" in sys.argv[1:]:
        selected["prepared"] = prepare_frames(selected)
        selected = {**startup_screen(), "prepared": selected["prepared"]}
    selected["frames"] = len(selected.get("frames", []))
    print(json.dumps(selected, indent=2))
