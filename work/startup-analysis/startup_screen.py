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
import math
import os
import shutil
import struct
import sys
import threading
import time
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
CUSTOM = Path(__file__).resolve().parent / "custom"
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


def pdds_size(path):
    with open(path, "rb") as stream:
        header = stream.read(20)
    return struct.unpack_from("<II", header, 12)[::-1] if header[:4] == b"PDDS" else None


def for_display(candidates, size, width, height):
    """Resource EVA draws on this display: the exact size, else the 10.25" file
    (_10). Some emblems' 10.25" resources are 800x300; they are stretched to
    the display (prepare_frames, and the viewer for the splash)."""
    candidates = sorted(candidates)
    exact = [path for path in candidates if size(path) == (width, height)]
    display = [path for path in candidates if path.stem.endswith("_10") and size(path)]
    return (exact or display or [None])[0]


def frames_folder(emblem, source, width, height):
    """frames/eva_ani_0x<emblem>, or ..._<w>x<h> for a smaller animation
    stretched to the display (800x300 -> 1280x480, the same aspect ratio)."""
    name = f"eva_ani_0x{emblem:02X}"
    return FRAMES / (name if pdds_size(source) == (width, height) else f"{name}_{width}x{height}")


def stretch(rgb, width, height, target_width, target_height):
    """Nearest-neighbour stretch of packed RGB. Columns repeat with period
    target_width/gcd, so each output column phase is one C-level slice copy."""
    group = math.gcd(width, target_width)
    source_step, target_step = width // group, target_width // group
    wide = bytearray(target_width * height * 3)
    for phase in range(target_step):
        column = phase * source_step // target_step
        for channel in range(3):
            wide[phase * 3 + channel::target_step * 3] = rgb[column * 3 + channel::source_step * 3]
    row = target_width * 3
    return b"".join(wide[(y * height // target_height) * row:(y * height // target_height + 1) * row]
                    for y in range(target_height))


def startup_screen(width=1280, height=480):
    """{'type', 'emblem', 'splash', 'frames', ...} for the viewer, or {'error'}."""
    try:
        records = json.loads(SCHEMA.read_text())["records"]
        memory = read_ncd(NCD)
        kind = TYPES.get(coded_value(memory, records, "STARTUP_TYPE"), "black")
        emblem = coded_value(memory, records, "STARTUP_EMBLEM")
    except (OSError, ValueError, KeyError, StopIteration) as error:
        return {"error": f"coding unavailable: {error!r}", "ncd": str(NCD)}
    result = {"type": kind, "emblem": emblem, "ncd": str(NCD), "splash": None, "frames": [],
              "display": [width, height]}
    custom = CUSTOM / f"eva_0x{emblem:02X}"
    if custom.is_dir():
        # User-made startup replacing the firmware's for this emblem (make_custom_startup.py).
        result["custom"] = str(custom)
        if (custom / "splash.png").is_file():
            result["splash"] = str(custom / "splash.png")
        if kind == "animation":
            result["frames"] = [str(p) for p in sorted(custom.glob("frame_*.png"))]
        return result
    images = eva_images()
    if images is None:
        result["error"] = "EVA images not found in outputs/NBT_files"
        return result
    # EVA keeps one file per display (07 = 7", 10 = 10.25").
    splash = for_display(images.glob(f"eva_splash_0x{emblem:02X}_*.png"), png_size, width, height)
    if splash:
        result["splash"] = str(splash)
    if kind == "animation":
        source = for_display(images.glob(f"eva_ani_0x{emblem:02X}_*.pdds"), pdds_size, width, height)
        if source:
            result["animation_source"] = str(source)
            animation = frames_folder(emblem, source, width, height)
            if animation.is_dir():
                result["frames"] = [str(p) for p in sorted(animation.glob("frame_*.png"))]
    return result


def prepare_frames(choice):
    """Decode the coded animation into its frames folder (once), stretched to
    the display when smaller. Each decoder writes its own temporary folder and
    renames it, so a partial decode is never used and a concurrent decoder
    (viewer and --prepare-all) cannot interfere; folders left by an
    interrupted decode more than an hour ago are discarded."""
    source = choice.get("animation_source")
    width, height = choice.get("display", (1280, 480))
    if not source:
        return False
    target = frames_folder(choice["emblem"], source, width, height)
    if choice.get("frames") or target.is_dir():
        return False
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import pdds
    for stale in FRAMES.glob(target.name + ".*tmp"):
        if time.time() - stale.stat().st_mtime > 3600:
            shutil.rmtree(stale, ignore_errors=True)
    temporary = target.with_name(f"{target.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    temporary.mkdir(parents=True)
    info = pdds.read_pdds(source)
    for index, blocks in pdds.frames(source):
        rgb = pdds.dxt1_to_rgb(blocks, info["width"], info["height"])
        if (info["width"], info["height"]) != (width, height):
            rgb = stretch(rgb, info["width"], info["height"], width, height)
        pdds.write_png(temporary / f"frame_{index:03d}.png", rgb, width, height)
    try:
        temporary.rename(target)
    except OSError:
        if not target.is_dir():
            raise
        shutil.rmtree(temporary)  # another decoder finished first
        return False
    return True


def prepare_all(width=1280, height=480):
    """Decode every emblem's startup animation for this display (once each)."""
    images = eva_images()
    prepared = []
    if images is None:
        return prepared
    for emblem in sorted({int(p.stem.split("_")[2], 16) for p in images.glob("eva_ani_0x*_*.pdds")}):
        source = for_display(images.glob(f"eva_ani_0x{emblem:02X}_*.pdds"), pdds_size, width, height)
        if source and prepare_frames({"animation_source": str(source), "emblem": emblem,
                                      "display": (width, height)}):
            prepared.append(source.name)
            print("decoded", source.name, flush=True)
    return prepared


if __name__ == "__main__":
    if "--prepare-all" in sys.argv[1:]:
        print(json.dumps({"prepared": prepare_all()}, indent=2))
        sys.exit(0)
    selected = startup_screen()
    if "--prepare" in sys.argv[1:]:
        selected["prepared"] = prepare_frames(selected)
        selected = {**startup_screen(), "prepared": selected["prepared"]}
    selected["frames"] = len(selected.get("frames", []))
    print(json.dumps(selected, indent=2))
