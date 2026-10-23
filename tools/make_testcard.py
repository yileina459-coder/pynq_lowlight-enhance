#!/usr/bin/env python3
"""Draw the standard demo test card at the panel's native size.

Why this exists
    The first card was drawn on a 1600x900 canvas with Pillow's default bitmap font - about 11
    pixels tall - and then scaled to 640x480. The text ended up around 4 pixels high, which no
    amount of contrast enhancement can make legible. That was a defect in the test asset, not in
    the pipeline, and it is worth having a card that is drawn at the size it will be shown at.

What it contains, and why each part is there
    title        large text: the first thing a viewer judges
    body         three font sizes, so "can this preset make small text readable" has an answer
    dark page    a dark panel with light text: the case the document/night presets exist for
    grey ramp    a continuous ramp: shows clipping and the tone curve
    fine lines   one-pixel stripes: sharpening and binarising both change these visibly
    colour chips saturated patches: shows whether colour survives the processing

Usage
    python tools/make_testcard.py
    python tools/make_testcard.py --out card.png --width 1280 --height 960   # 2x variant
"""

from __future__ import annotations

import argparse
import sys

from PIL import Image, ImageDraw, ImageFont

FONT_CANDIDATES = [
    r"C:\Windows\Fonts\arialbd.ttf",
    r"C:\Windows\Fonts\arial.ttf",
    r"C:\Windows\Fonts\seguisb.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]
MONO_CANDIDATES = [
    r"C:\Windows\Fonts\consola.ttf",
    r"C:\Windows\Fonts\lucon.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
]


def load_font(candidates: list[str], size: int) -> ImageFont.FreeTypeFont:
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except Exception:                                  # noqa: BLE001
            continue
    print("warning: no scalable font found, falling back to the bitmap default "
          "(text will be tiny)", file=sys.stderr)
    return ImageFont.load_default()


def build(width: int, height: int) -> Image.Image:
    scale = width / 640.0
    img = Image.new("RGB", (width, height), (18, 18, 20))
    d = ImageDraw.Draw(img)

    def s(value: float) -> int:
        return max(1, int(round(value * scale)))

    title = load_font(FONT_CANDIDATES, s(34))
    body_l = load_font(MONO_CANDIDATES, s(20))
    body_m = load_font(MONO_CANDIDATES, s(15))
    body_s = load_font(MONO_CANDIDATES, s(11))

    # --- title -----------------------------------------------------------------
    d.text((s(14), s(8)), "LOW-LIGHT OBSERVATION TEST", font=title, fill=(250, 250, 250))
    d.line([(s(14), s(50)), (width - s(14), s(50))], fill=(120, 120, 130), width=s(2))

    # --- light page with three font sizes -------------------------------------
    d.rectangle([s(14), s(58), width - s(14), s(268)], fill=(236, 234, 226))
    d.text((s(24), s(66)), "The quick brown fox jumps over the lazy dog", 
           font=body_l, fill=(20, 20, 24))
    d.text((s(24), s(94)), "SPHINX OF BLACK QUARTZ, JUDGE MY VOW", 
           font=body_l, fill=(20, 20, 24))
    d.text((s(24), s(126)), "Medium: 0123456789  the five boxing wizards jump quickly",
           font=body_m, fill=(30, 30, 34))
    d.text((s(24), s(150)), "Small : 0123456789  pack my box with five dozen jugs",
           font=body_s, fill=(40, 40, 44))
    d.text((s(24), s(172)), "Tiny  : 0123456789  how vexingly quick daft zebras jump",
           font=body_s, fill=(60, 60, 64))
    for i, chip in enumerate([(200, 40, 40), (40, 170, 60), (50, 80, 200),
                              (230, 200, 40), (200, 60, 200), (40, 200, 200)]):
        x = s(24) + i * s(52)
        d.rectangle([x, s(198), x + s(44), s(240)], fill=chip)
    d.text((s(24), s(246)), "colour chips keep their hue in mono=0 presets",
           font=body_s, fill=(50, 50, 54))

    # --- dark page ------------------------------------------------------------
    d.rectangle([s(14), s(276), width - s(14), s(352)], fill=(12, 12, 16))
    d.text((s(24), s(284)), "DARK PAGE - this is what document/night are for",
           font=body_m, fill=(210, 210, 210))
    d.text((s(24), s(306)), "faint text on black must become readable", 
           font=body_m, fill=(90, 90, 96))
    d.text((s(24), s(326)), "and stay the same polarity (dark ink, light page)",
           font=body_s, fill=(70, 70, 76))

    # --- grey ramp and fine detail -------------------------------------------
    for x in range(s(14), width - s(14)):
        v = int(255 * (x - s(14)) / max(1, (width - s(28))))
        d.line([(x, s(360)), (x, s(400))], fill=(v, v, v))
    d.text((s(16), s(402)), "0", font=body_s, fill=(200, 200, 200))
    d.text((width - s(30), s(402)), "255", font=body_s, fill=(200, 200, 200))

    # One-pixel stripes at two densities: sharpening halos and binarisation both show up here.
    for x in range(s(14), width - s(14), s(4)):
        d.line([(x, s(420)), (min(x + s(2), width - s(14)), s(420) + s(24))],
               fill=(240, 240, 240), width=1)
    for x in range(s(14), width - s(14), s(2)):
        d.line([(x, s(452)), (x, s(452) + s(18))], fill=(120, 200, 255), width=1)

    return img


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="data/images/testcard_640x480.png")
    ap.add_argument("--width", type=int, default=640)
    ap.add_argument("--height", type=int, default=480)
    args = ap.parse_args(argv)

    img = build(args.width, args.height)
    img.save(args.out)
    print(f"wrote {args.out} ({args.width}x{args.height})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
