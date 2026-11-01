# © 2026 davisod & JEtsKi
"""Custom startup screen: THE CLUSTER HUB (neon T sign, light beam reveal, glowing orb).

Writes custom/eva_0x<emblem>/frame_000.png ... and splash.png (1280x480).
startup_screen.py prefers a custom/eva_0x<emblem>/ folder over the firmware's
EVA resources for that emblem; delete the folder to restore the original.
The neon T is drawn from lines after the community avatar and the title uses
a system font; neither is the original artwork.
Requires Pillow (only for generating the frames, not for running the emulator).
Usage:
  py -3 make_cluster_hub_startup.py [EMBLEM]      (default 0x09, the Christmas one)
"""
import math
import random
import shutil
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

WIDTH, HEIGHT = 1280, 480
FRAMES = 150
NEON = (40, 150, 255)
CORE = (190, 235, 255)
BEAM = (120, 230, 255)
TITLE = "THE CLUSTER HUB"
CUSTOM = Path(__file__).resolve().parent / "custom"


def clamp(t):
    return min(1.0, max(0.0, t))


def ease_out(t):
    return 1 - (1 - clamp(t)) ** 3


def ease_in_out(t):
    t = clamp(t)
    return t * t * (3 - 2 * t)


def background():
    small = Image.new("RGB", (160, 60))
    pixels = small.load()
    for y in range(60):
        for x in range(160):
            d = min(1.0, math.hypot((x - 80) / 90, (y - 26) / 44))
            k = 1 - d ** 1.4
            pixels[x, y] = (int(4 + 8 * k), int(10 + 30 * k), int(16 + 46 * k))
    image = small.resize((WIDTH, HEIGHT), Image.BICUBIC)
    # Faint perspective grid on the floor.
    grid = Image.new("L", (WIDTH, HEIGHT), 0)
    draw = ImageDraw.Draw(grid)
    horizon = 330
    for i in range(-24, 25):
        draw.line((WIDTH / 2 + i * 18, horizon, WIDTH / 2 + i * 150, HEIGHT), fill=60, width=1)
    for j in range(8):
        y = horizon + (HEIGHT - horizon) * (j / 8) ** 1.8
        draw.line((0, y, WIDTH, y), fill=int(25 + 40 * j / 8), width=1)
    fade = Image.linear_gradient("L").resize((WIDTH, HEIGHT - horizon))
    mask = Image.new("L", (WIDTH, HEIGHT), 0)
    mask.paste(fade, (0, horizon))
    grid = ImageChops.multiply(grid, mask)
    tint = Image.new("RGB", (WIDTH, HEIGHT), (30, 120, 200))
    return Image.composite(tint, image, grid.point(lambda a: a // 2))


def orb(radius):
    """Blue/violet glowing sphere like the banner's."""
    size = radius * 2
    small = Image.new("RGBA", (64, 64))
    pixels = small.load()
    for y in range(64):
        for x in range(64):
            dx, dy = (x - 32) / 32, (y - 32) / 32
            d = math.hypot(dx, dy)
            if d > 1:
                continue
            light = clamp(1 - math.hypot(dx + .35, dy + .35) / 1.3)
            violet = clamp((dx - dy) * .6 + .3)
            r = int(40 + 150 * violet + 80 * light)
            g = int(70 + 60 * light)
            b = int(200 + 55 * light)
            pixels[x, y] = (min(r, 255), min(g, 255), min(b, 255), int(255 * clamp((1 - d) * 6)))
    return small.resize((size, size), Image.BICUBIC)


def t_outline(scale):
    """Neon tube T: an outlined T with a small offset inner stroke, like the logo."""
    s = scale
    outer = [(-1.0, -1.2), (1.0, -1.2), (1.0, -.7), (.25, -.7), (.25, 1.25), (-.25, 1.25), (-.25, -.7), (-1.0, -.7)]
    inner = [(-.7, -.95), (.55, -.95)]
    stem = [(.0, -.45), (.0, .9), (-.12, 1.0)]
    return [[(x * s, y * s) for x, y in shape] for shape in (outer + outer[:1], inner, stem)]


def neon_sign(scale, power, flicker):
    size = int(scale * 5)
    layer = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(layer)
    for path in t_outline(scale):
        draw.line([(x + size / 2, y + size / 2) for x, y in path], fill=255, width=max(3, int(scale * .07)), joint="curve")
    level = power * flicker
    glow_wide = layer.filter(ImageFilter.GaussianBlur(scale * .28)).point(lambda a: int(min(255, a * 2.2 * level)))
    glow = layer.filter(ImageFilter.GaussianBlur(scale * .08)).point(lambda a: int(min(255, a * 1.6 * level)))
    tube = layer.point(lambda a: int(a * level))
    out = Image.new("RGBA", (size, size), NEON + (0,))
    out.putalpha(glow_wide)
    for colour, alpha in ((NEON, glow), (CORE, tube)):
        piece = Image.new("RGBA", (size, size), colour + (0,))
        piece.putalpha(alpha)
        out = Image.alpha_composite(out, piece)
    return out


def font(size):
    for path in ("C:/Windows/Fonts/ariblk.ttf", "C:/Windows/Fonts/impact.ttf", "C:/Windows/Fonts/segoeuib.ttf"):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            pass
    return ImageFont.load_default()


def title():
    face = font(84)
    box = face.getbbox(TITLE)
    layer = Image.new("RGBA", (box[2] - box[0] + 40, box[3] - box[1] + 40), (0, 0, 0, 0))
    ImageDraw.Draw(layer).text((20 - box[0], 20 - box[1]), TITLE, font=face, fill=(255, 255, 255, 255))
    glow = Image.new("RGBA", layer.size, BEAM + (0,))
    glow.putalpha(layer.getchannel("A").filter(ImageFilter.GaussianBlur(10)).point(lambda a: a // 2))
    return Image.alpha_composite(glow, layer)


random.seed(3)
# Neon sign start-up: off/on stutter before it settles.
FLICKER = [0, 0, 1, 0, 0, 1, 1, 0, .4, 1, 1, 1, 0, 1] + [1] * FRAMES


def frame(index, base, ball, text):
    t = index / (FRAMES - 1)
    image = base.copy().convert("RGBA")
    # Orb rises softly behind the lockup and breathes.
    orb_in = ease_out((t - .05) / .35)
    if orb_in > 0:
        pulse = 1 + .03 * math.sin(t * math.pi * 4)
        size = int(ball.width * (.85 + .15 * orb_in) * pulse)
        sphere = ball.resize((size, size), Image.BICUBIC)
        pad = 120
        halo_mask = Image.new("L", (size + 2 * pad, size + 2 * pad), 0)
        halo_mask.paste(sphere.getchannel("A"), (pad, pad))
        halo_mask = halo_mask.filter(ImageFilter.GaussianBlur(45)).point(lambda a: int(a * .55 * orb_in))
        halo = Image.new("RGBA", halo_mask.size, (90, 80, 230, 0))
        halo.putalpha(halo_mask)
        x, y = int(WIDTH * .62 - size / 2), int(HEIGHT * .46 - size / 2)
        image.alpha_composite(halo, (x - pad, y - pad))
        sphere.putalpha(sphere.getchannel("A").point(lambda a: int(a * .5 * orb_in)))
        image.alpha_composite(sphere, (x, y))
    # Neon T flickers on centred, then slides left of the title.
    sign_scale = 70
    gap = 30
    lockup = sign_scale * 2.1 + gap + text.width
    slide = ease_in_out((t - .32) / .2)
    final_x = WIDTH / 2 - lockup / 2 + sign_scale * 1.05
    sign_x = WIDTH / 2 + (final_x - WIDTH / 2) * slide
    sign = neon_sign(sign_scale, 1.0, FLICKER[index] if index < len(FLICKER) else 1)
    image.alpha_composite(sign, (int(sign_x - sign.width / 2), int(HEIGHT / 2 - sign.height / 2)))
    # A light beam sweeps across and reveals the title behind it.
    sweep = ease_in_out((t - .48) / .26)
    text_x = int(sign_x + sign_scale * 1.05 + gap - 20)
    text_y = int(HEIGHT / 2 - text.height / 2)
    beam_x = text_x - 60 + (text.width + 160) * sweep
    if sweep > 0:
        shown = text.copy()
        mask = Image.new("L", text.size, 0)
        ImageDraw.Draw(mask).rectangle((0, 0, max(0, beam_x - text_x), text.height), fill=255)
        mask = mask.filter(ImageFilter.GaussianBlur(6))
        shown.putalpha(ImageChops.multiply(shown.getchannel("A"), mask))
        image.alpha_composite(shown, (text_x, text_y))
    beam_alpha = math.sin(math.pi * clamp((t - .46) / .32))
    if beam_alpha > 0:
        beam = Image.new("L", (WIDTH, HEIGHT), 0)
        ImageDraw.Draw(beam).line((beam_x - 70, HEIGHT / 2 + 180, beam_x + 70, HEIGHT / 2 - 180), fill=255, width=4)
        glow = beam.filter(ImageFilter.GaussianBlur(14)).point(lambda a: min(255, a * 3))
        for alpha, colour in ((glow, BEAM), (beam, (255, 255, 255))):
            layer = Image.new("RGBA", (WIDTH, HEIGHT), colour + (0,))
            layer.putalpha(alpha.point(lambda a: int(a * beam_alpha)))
            image.alpha_composite(layer)
    return image.convert("RGB")


def main():
    emblem = int(sys.argv[1], 16) if len(sys.argv) > 1 else 0x09
    target = CUSTOM / f"eva_0x{emblem:02X}"
    temporary = target.with_name(target.name + ".tmp")
    if temporary.exists():
        shutil.rmtree(temporary)
    temporary.mkdir(parents=True)
    base, ball, text = background(), orb(190), title()
    for index in range(FRAMES):
        image = frame(index, base, ball, text)
        image.save(temporary / f"frame_{index:03d}.png")
    image.save(temporary / "splash.png")
    if target.exists():
        shutil.rmtree(target)      # replace the previous custom version only
    temporary.rename(target)
    print("custom startup written:", target)


if __name__ == "__main__":
    main()
