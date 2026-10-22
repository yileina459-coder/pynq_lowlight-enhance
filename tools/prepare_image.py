#!/usr/bin/env python3
"""Turn any picture into the 640x480 PNG the board displays, with a predictable fit.

Why a separate step
    The board can resize by itself, but doing it here means the operator sees exactly what the
    panel will show (including the letterbox bars) before it goes over the network, and the upload
    is a plain PNG that Pillow opens without surprises.

Fits
    letterbox  keep the aspect ratio, pad with the background colour (default: black)
    crop       keep the aspect ratio, fill the frame and cut the overflow (no bars)
    stretch    ignore the aspect ratio and fill the frame (faces get wider)

    python tools/prepare_image.py photo.jpg --out out/mine_640x480.png
    python tools/prepare_image.py photo.jpg --fit crop --background 32
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

WIDTH, HEIGHT = 640, 480


def load(path: str) -> Image.Image:
    """Open any picture Pillow understands, honouring EXIF orientation (phone photos)."""
    img = Image.open(path)
    img = ImageOps.exif_transpose(img)
    return img.convert("RGB")


def fit(img: Image.Image, mode: str, background: int) -> Image.Image:
    if mode == "stretch":
        return img.resize((WIDTH, HEIGHT), Image.LANCZOS)

    src_w, src_h = img.size
    scale = (WIDTH / src_w) if mode == "crop" else min(WIDTH / src_w, HEIGHT / src_h)
    scale = max(scale, HEIGHT / src_h) if mode == "crop" else scale
    new_w, new_h = max(1, round(src_w * scale)), max(1, round(src_h * scale))
    resized = img.resize((new_w, new_h), Image.LANCZOS)

    canvas = Image.new("RGB", (WIDTH, HEIGHT), (background, background, background))
    if mode == "crop":
        left = (new_w - WIDTH) // 2
        top = (new_h - HEIGHT) // 2
        canvas.paste(resized, (-left, -top))
    else:
        canvas.paste(resized, ((WIDTH - new_w) // 2, (HEIGHT - new_h) // 2))
    return canvas


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("image", help="source picture (any format Pillow reads)")
    ap.add_argument("--out", required=True, help="output PNG path")
    ap.add_argument("--fit", choices=("letterbox", "crop", "stretch"), default="letterbox")
    ap.add_argument("--background", type=int, default=0, help="letterbox colour 0..255")
    args = ap.parse_args(argv)

    source = Path(args.image)
    if not source.is_file():
        print(f"PREPARE FAIL: no such file: {source}")
        return 1

    img = load(str(source))
    fitted = fit(img, args.fit, args.background)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    fitted.save(out, "PNG")

    pixels = np.asarray(fitted)
    print(f"source {img.size[0]}x{img.size[1]} -> {WIDTH}x{HEIGHT} ({args.fit})")
    print(f"wrote {out}  mean={pixels.mean():.1f}  min={pixels.min()}  max={pixels.max()}")
    if pixels.max() < 8:
        print("WARNING: the result is almost black - is the source picture dark?")
    return 0


if __name__ == "__main__":
    sys.exit(main())
