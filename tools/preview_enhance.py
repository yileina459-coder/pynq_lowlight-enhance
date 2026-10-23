#!/usr/bin/env python3
"""Preview what the board's kernel will do to a picture, without touching the board.

Why this exists
    The kernel already brightens: it has local contrast plus a two-segment tone curve with a
    separate gain below and above a knee, and the presets 'reading' / 'document' / 'night' use
    large low-end gains (up to 7.5x). The operator could not see any of that, because the upload
    path always wrote preset 'pass', which is identity - so the picture looked unchanged and the
    hardware looked incapable.

    This reimplements the kernel exactly (stage 1..5 of src/hls/enhance/enhance_body.inc) so a
    picture can be tried before uploading, and so "which preset fits this photo" is answered by
    looking rather than guessing.

    python tools/preview_enhance.py photo.jpg --preset night --out preview.png
    python tools/preview_enhance.py photo.jpg --sheet --out sheet.png     # all presets

Layout of the sheet: source, then one tile per preset, labelled with its name.
"""

from __future__ import annotations

import argparse
import sys

import numpy as np
from PIL import Image, ImageDraw

WIDTH, HEIGHT = 640, 480

# Same table as board/hdmi_stream_enhance/hdmi_live.py. Kept in one place conceptually; if a preset
# changes there it must change here too, which tools/check_presets.py enforces.
PRESETS = {
    # The tone curve is two-segment (below/above `knee`, with separate gains), so these numbers are
    # what decides "the picture got brighter". `clarity` adds local contrast.
    #
    # The first four are the honest "pass through" options; the rest trade clipping for visibility.
    # Values were chosen with tools/preview_enhance.py, which reimplements the kernel exactly:
    # 'bright' lifts a very dark picture (mean 33 -> 116) with under 3% blown highlights, while an
    # aggressive curve (gain_lo 64+) reaches 129 but blows ~39% of the frame, which is why it is
    # not the default.
    "pass":     dict(clarity=16, knee=255, gain_lo=16, gain_hi=16),
    "clarity":  dict(clarity=28, knee=255, gain_lo=16, gain_hi=16),
    # Sharper local contrast for text that has already been brightened on the PC. Safe only where
    # clipping has headroom: the sweep in tools/tune_clarity.py puts the crossover at about clarity=32
    # for photographs and 48 for pages, so this preset is chosen per picture, never as a default.
    "crisp":    dict(clarity=48, knee=255, gain_lo=16, gain_hi=16),
    "bright":   dict(clarity=24, knee=192, gain_lo=56, gain_hi=20),
    "night":    dict(clarity=28, knee=224, gain_lo=72, gain_hi=24),
    "document": dict(clarity=20, knee=192, gain_lo=64, gain_hi=16),
    "reading":  dict(clarity=24, knee=48, gain_lo=88, gain_hi=14),
    "invert":   dict(clarity=24, knee=192, gain_lo=56, gain_hi=20, invert=1, mono=1),
    "binarize": dict(clarity=16, knee=64, gain_lo=112, gain_hi=8,
                     thresh=112, binarize=1, mono=1),
    "split":    dict(clarity=28, knee=90, gain_lo=40, gain_hi=12, split_x=320),
}


def luma(rgb: np.ndarray) -> np.ndarray:
    """enh_luma: the kernel's fixed-point luma, 0..255."""
    r = rgb[..., 0].astype(np.int32)
    g = rgb[..., 1].astype(np.int32)
    b = rgb[..., 2].astype(np.int32)
    return ((77 * r + 150 * g + 29 * b) >> 8).astype(np.int32)


def _gauss_121(y: np.ndarray) -> np.ndarray:
    """The 1-2-1 Gaussian over a 3x3 window, replicated at the borders.

    Separable: 1-2-1 across rows, then 1-2-1 down columns, with a single >>4 at the end. The horizontal
    pass deliberately does not shift - shifting twice would round twice, and the result would no longer
    match the nine-tap version that this replaces. For 8-bit input the intermediate (max 4 * 255 = 1020,
    times 4 vertically = 4080) stays well inside int32.

    Two passes over three shifted arrays instead of one pass over nine: about twice as fast in the
    measurement below, which matters because every preset evaluation in every frame goes through here.
    """
    padded = np.pad(y, 1, mode="edge")
    # Horizontal 1-2-1, no shift.
    horizontal = (padded[:, :-2] + 2 * padded[:, 1:-1] + padded[:, 2:])
    # Vertical 1-2-1, then the single shift by 4.
    total = (horizontal[:-2, :] + 2 * horizontal[1:-1, :] + horizontal[2:, :])
    return total >> 4


def box_mean(y: np.ndarray) -> np.ndarray:
    return _gauss_121(y)


def enhance(rgb: np.ndarray, preset: dict) -> np.ndarray:
    clarity = preset.get("clarity", 16)
    knee = preset.get("knee", 255)
    gain_lo = preset.get("gain_lo", 16)
    gain_hi = preset.get("gain_hi", 16)
    thresh = preset.get("thresh", 128)
    binarize = preset.get("binarize", 0)
    invert = preset.get("invert", 0)
    mono = preset.get("mono", 0)
    split_x = preset.get("split_x", 0)

    y = luma(rgb)

    # stage 2: local contrast
    mean = box_mean(y)
    detail = y - mean
    y1 = mean + ((clarity * detail) >> 4)
    y1 = np.clip(y1, 0, 255)

    # stage 3: two-segment tone curve
    below = (y1 * gain_lo) >> 4
    above = knee + (((y1 - knee) * gain_hi) >> 4)
    y2 = np.where(y1 <= knee, below, above)
    y2 = np.clip(y2, 0, 255)

    # stage 4: binarise / invert
    y3 = np.where(y2 >= thresh, 255, 0) if binarize else y2
    if invert:
        y3 = 255 - y3

    # stage 5: colour. Chroma survives as a common offset, unless mono.
    delta = (y3 - y).astype(np.int32)[..., None]
    shifted = np.clip(rgb.astype(np.int32) + delta, 0, 255)
    out = np.where(mono, np.repeat(y3[..., None], 3, axis=2), shifted).astype(np.uint8)

    # split screen: the left of split_x stays untouched
    if split_x:
        out = out.copy()
        out[:, :split_x] = rgb[:, :split_x]
    return out


def load(path: str) -> np.ndarray:
    from PIL import ImageOps
    img = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    scale = min(WIDTH / img.width, HEIGHT / img.height)
    size = (max(1, round(img.width * scale)), max(1, round(img.height * scale)))
    canvas = Image.new("RGB", (WIDTH, HEIGHT), (0, 0, 0))
    canvas.paste(img.resize(size, Image.LANCZOS),
                 ((WIDTH - size[0]) // 2, (HEIGHT - size[1]) // 2))
    return np.asarray(canvas)


def stats(rgb: np.ndarray) -> str:
    y = luma(rgb)
    dark = (y < 64).mean() * 100
    bright = (y > 192).mean() * 100
    return (f"mean={y.mean():5.1f} p10={np.percentile(y, 10):3.0f} "
            f"p90={np.percentile(y, 90):3.0f} dark={dark:4.1f}% bright={bright:4.1f}%")


def make_sheet(rgb: np.ndarray, names: list[str]) -> Image.Image:
    cols, rows = 3, (len(names) + 1 + 2) // 3
    tile_w, tile_h = WIDTH // 2, HEIGHT // 2
    sheet = Image.new("RGB", (cols * tile_w, rows * (tile_h + 18)), (24, 24, 24))
    draw = ImageDraw.Draw(sheet)

    def place(index: int, image: np.ndarray, label: str) -> None:
        col, row = index % cols, index // cols
        x, y = col * tile_w, row * (tile_h + 18)
        sheet.paste(Image.fromarray(image).resize((tile_w, tile_h), Image.LANCZOS), (x, y + 18))
        draw.text((x + 4, y + 4), label, fill=(230, 230, 230))

    place(0, rgb, f"source  {stats(rgb)}")
    for i, name in enumerate(names, start=1):
        out = enhance(rgb, PRESETS[name])
        place(i, out, f"{name}  {stats(out)}")
    return sheet


def score_preset(out: np.ndarray) -> float:
    """How usable the result would be, higher is better.

    A dark picture is only 'better' if it gets readable *and* keeps detail: a curve aggressive
    enough to blow a third of the frame scores badly even though its mean looks nice.
    """
    y = luma(out)
    mean = y.mean()
    clipped = (y > 250).mean() * 100
    spread = np.percentile(y, 95) - np.percentile(y, 5)

    penalty = 0.0
    if mean < 100:
        penalty += (100 - mean) * 1.5
    if mean > 175:
        penalty += (mean - 175) * 1.5
    if clipped > 12:
        penalty += (clipped - 12) * 2.0
    return float(spread - penalty)


def recommend(rgb: np.ndarray) -> tuple[str, float, str]:
    """Pick the preset whose result is most usable for this specific picture."""
    best, best_score, best_stats = "pass", None, ""
    # Only the tone-curve presets are candidates. invert/binarize turn a photo into text-mode
    # output and 'split' is a side-by-side demonstration, so none of them is a sensible automatic
    # choice for a picture someone just uploaded.
    #
    # 'crisp' is excluded as well: it sharpens a page by 37% but crushes about 6% of a photograph's
    # shadows to pure black, and telling a page from a photograph reliably is the classification that
    # has misfired before. The preset is offered in the panel's dropdown instead, where a person decides.
    manual_only = {"split", "invert", "binarize", "crisp"}
    for name, preset in PRESETS.items():
        if name in manual_only:
            continue
        out = enhance(rgb, preset)
        s = score_preset(out)
        if best_score is None or s > best_score:
            best, best_score, best_stats = name, s, stats(out)
    return best, best_score, best_stats


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("image")
    ap.add_argument("--preset", default="night", choices=sorted(PRESETS))
    ap.add_argument("--sheet", action="store_true", help="one tile per preset")
    ap.add_argument("--out", default="", help="output PNG (not needed with --recommend)")
    ap.add_argument("--recommend", action="store_true",
                    help="pick the preset that suits this picture and print RECOMMEND=<name>")
    args = ap.parse_args(argv)

    rgb = load(args.image)
    print(f"source {args.image}: {stats(rgb)}")

    if args.recommend:
        best, best_score, detail = recommend(rgb)
        print(f"RECOMMEND={best}")
        print(f"  {detail}")
        return 0

    if args.sheet:
        names = [n for n in PRESETS if n != "split"] + ["split"]
        Image.fromarray(rgb).save(args.out.replace(".png", "_source.png"))
        make_sheet(rgb, names).save(args.out)
        print(f"wrote {args.out} ({len(names) + 1} tiles)")
        for name in names:
            print(f"  {name:9s} {stats(enhance(rgb, PRESETS[name]))}")
        return 0

    out = enhance(rgb, PRESETS[args.preset])
    Image.fromarray(out).save(args.out)
    print(f"preset {args.preset}: {stats(out)}")
    print(f"wrote {args.out}")

    gain = PRESETS[args.preset].get("gain_lo", 16) / 16
    if gain > 1.5 and luma(rgb).mean() < 90:
        print(f"note: gain_lo={gain:.1f}x lifts shadows, which suits this dark source")
    return 0


if __name__ == "__main__":
    sys.exit(main())
