# © 2026 davisod & JEtsKi
"""Custom startup screen: a Claude-style spark and wordmark animation.

Writes custom/eva_0x<emblem>/frame_000.png ... and splash.png (1280x480).
startup_screen.py prefers a custom/eva_0x<emblem>/ folder over the firmware's
EVA resources for that emblem; delete the folder to restore the original.
The spark is drawn from geometry and the wordmark uses a system font; neither
is the official artwork.
Requires Pillow (only for generating the frames, not for running the emulator).
Usage:
  py -3 make_custom_startup.py [EMBLEM]      (default 0x09, the Christmas one)
"""
import math
import random
import shutil
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

WIDTH, HEIGHT = 1280, 480
FRAMES = 150                       # 40 ms each in the viewer: 6 s
ORANGE = (217, 119, 87)            # #D97757
TEXT = (240, 234, 226)
SCALE = 3                          # supersampling for the spark
CUSTOM = Path(__file__).resolve().parent / "custom"
FONTS = ("C:/Windows/Fonts/georgia.ttf", "C:/Windows/Fonts/segoeui.ttf")


def ease_out(t):
    t = min(1.0, max(0.0, t))
    return 1 - (1 - t) ** 3


def ease_in_out(t):
    t = min(1.0, max(0.0, t))
    return t * t * (3 - 2 * t)


def background():
    """Dark warm radial gradient (computed small, scaled up smoothly)."""
    small = Image.new("RGB", (160, 60))
    pixels = small.load()
    for y in range(60):
        for x in range(160):
            d = min(1.0, math.hypot((x - 80) / 80, (y - 30) / 40))
            k = 1 - d ** 1.5
            pixels[x, y] = (int(12 + 22 * k), int(10 + 14 * k), int(9 + 10 * k))
    return small.resize((WIDTH, HEIGHT), Image.BICUBIC)


# Twelve tapered rays with slightly irregular lengths and angles, as in the mark.
random.seed(7)
RAYS = [(i * 30 + random.uniform(-6, 6), random.uniform(.78, 1.0), random.uniform(0, .25)) for i in range(12)]


def spark(radius, growth, rotation):
    """RGBA spark of the given outer radius; growth 0..1 per ray (staggered)."""
    size = int(radius * 2.4) * SCALE
    layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    centre = size / 2
    for angle, length, delay in RAYS:
        grown = ease_out((growth - delay) / (1 - delay)) if growth > delay else 0
        if grown <= 0:
            continue
        a = math.radians(angle + rotation)
        outer = radius * length * grown * SCALE
        inner = radius * .08 * SCALE
        half = radius * .085 * SCALE
        ux, uy = math.cos(a), math.sin(a)
        px, py = -uy, ux
        # Wide at the centre, rounded tip.
        tip_half = half * .45
        points = [(centre + ux * inner + px * half, centre + uy * inner + py * half),
                  (centre + ux * outer + px * tip_half, centre + uy * outer + py * tip_half),
                  (centre + ux * outer - px * tip_half, centre + uy * outer - py * tip_half),
                  (centre + ux * inner - px * half, centre + uy * inner - py * half)]
        draw.polygon(points, fill=ORANGE + (255,))
        tx, ty = centre + ux * outer, centre + uy * outer
        draw.ellipse((tx - tip_half, ty - tip_half, tx + tip_half, ty + tip_half), fill=ORANGE + (255,))
    if growth > 0:
        core = radius * .16 * ease_out(growth * 3) * SCALE
        draw.ellipse((centre - core, centre - core, centre + core, centre + core), fill=ORANGE + (255,))
    return layer.resize((size // SCALE, size // SCALE), Image.LANCZOS)


def font(size):
    for path in FONTS:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            pass
    return ImageFont.load_default()


def wordmark():
    face = font(118)
    box = face.getbbox("Claude")
    layer = Image.new("RGBA", (box[2] - box[0] + 20, box[3] - box[1] + 30), (0, 0, 0, 0))
    ImageDraw.Draw(layer).text((10 - box[0], 15 - box[1]), "Claude", font=face, fill=TEXT + (255,))
    return layer


def frame(index, base, text):
    t = index / (FRAMES - 1)
    radius = 92
    growth = min(1.0, t / .42)
    rotation = -40 * (1 - ease_out(t / .42))
    # The spark grows centred, then moves left to make room for the wordmark.
    gap = 36
    lockup = radius * 2 + gap + text.width
    slide = ease_in_out((t - .42) / .25)
    spark_x = WIDTH / 2 + (WIDTH / 2 - lockup / 2 + radius - WIDTH / 2) * slide
    centre_y = HEIGHT / 2
    image = base.copy()
    mark = spark(radius, growth, rotation)
    glow_strength = .55 + .25 * math.sin(math.pi * min(1.0, max(0.0, (t - .3) / .5)))
    glow = mark.filter(ImageFilter.GaussianBlur(22))
    glow.putalpha(glow.getchannel("A").point(lambda a: int(a * glow_strength)))
    position = (int(spark_x - mark.width / 2), int(centre_y - mark.height / 2))
    image.paste(glow, position, glow)
    image.paste(mark, position, mark)
    fade = ease_in_out((t - .55) / .25)
    if fade > 0:
        shown = text.copy()
        shown.putalpha(shown.getchannel("A").point(lambda a: int(a * fade)))
        text_x = int(spark_x + radius + gap - 10 + 24 * (1 - fade))
        image.paste(shown, (text_x, int(centre_y - text.height / 2 - 6)), shown)
    return image


def main():
    emblem = int(sys.argv[1], 16) if len(sys.argv) > 1 else 0x09
    target = CUSTOM / f"eva_0x{emblem:02X}"
    temporary = target.with_name(target.name + ".tmp")
    if temporary.exists():
        shutil.rmtree(temporary)
    temporary.mkdir(parents=True)
    base, text = background(), wordmark()
    for index in range(FRAMES):
        image = frame(index, base, text)
        image.save(temporary / f"frame_{index:03d}.png")
    image.save(temporary / "splash.png")
    if target.exists():
        shutil.rmtree(target)      # replace the previous custom version only
    temporary.rename(target)
    print("custom startup written:", target)


if __name__ == "__main__":
    main()
