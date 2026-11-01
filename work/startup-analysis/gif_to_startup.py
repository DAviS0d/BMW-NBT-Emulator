# © 2026 davisod & JEtsKi
"""Custom startup screen from an animated GIF.

Writes custom/eva_0x<emblem>/frame_000.png ... and splash.png (1280x480).
startup_screen.py prefers a custom/eva_0x<emblem>/ folder over the firmware's
EVA resources for that emblem; delete the folder to restore the original.
The GIF is scaled to fill the display and centre-cropped (aspect ratio kept),
and resampled to the viewer's 40 ms per frame so it plays at its own speed.
The last frame stays on screen as the splash.
Requires Pillow (only for generating the frames, not for running the emulator).
Usage:
  py -3 gif_to_startup.py FILE.gif [EMBLEM]      (default 0x09, the Christmas one)
"""
import shutil
import sys
from pathlib import Path

from PIL import Image, ImageSequence

WIDTH, HEIGHT = 1280, 480
FRAME_MS = 40                      # the viewer shows one frame every 40 ms
CUSTOM = Path(__file__).resolve().parent / "custom"


def fill(image):
    """Scale to cover the display, then crop the centre."""
    scale = max(WIDTH / image.width, HEIGHT / image.height)
    w, h = round(image.width * scale), round(image.height * scale)
    big = image.resize((w, h), Image.LANCZOS)
    left, top = (w - WIDTH) // 2, (h - HEIGHT) // 2
    return big.crop((left, top, left + WIDTH, top + HEIGHT))


def timed_frames(path):
    """GIF frames sampled every FRAME_MS (each GIF frame lasts its own duration)."""
    frames, starts, now = [], [], 0
    with Image.open(path) as gif:
        for frame in ImageSequence.Iterator(gif):
            frames.append(frame.convert("RGB"))
            starts.append(now)
            now += frame.info.get("duration") or 100
    index = 0
    for tick in range(0, now, FRAME_MS):
        while index + 1 < len(frames) and starts[index + 1] <= tick:
            index += 1
        yield frames[index]


def main():
    source = Path(sys.argv[1])
    emblem = int(sys.argv[2], 16) if len(sys.argv) > 2 else 0x09
    target = CUSTOM / f"eva_0x{emblem:02X}"
    temporary = target.with_name(target.name + ".tmp")
    if temporary.exists():
        shutil.rmtree(temporary)
    temporary.mkdir(parents=True)
    count = 0
    for count, frame in enumerate(timed_frames(source), 1):
        image = fill(frame)
        image.save(temporary / f"frame_{count - 1:03d}.png")
    image.save(temporary / "splash.png")
    if target.exists():
        shutil.rmtree(target)      # replace the previous custom version only
    temporary.rename(target)
    print(f"custom startup written: {target} ({count} frames)")


if __name__ == "__main__":
    main()
