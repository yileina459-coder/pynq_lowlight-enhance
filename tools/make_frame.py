#!/usr/bin/env python3
"""Convert any picture into the raw frame format the board displays.

Why a PC-side converter
    The board runs PYNQ 3.1.1, which may or may not carry Pillow, and doing image decoding
    on the Zynq's ARM core would put CPU work on the path whose whole point is that the PL
    does the work. Converting once on the PC and shipping a plain 640x480x3 byte file keeps
    the board side trivial (``numpy.frombuffer``) and makes the data format obvious.

Aspect ratio
    The panel is 4:3 and the HDMI output is 640x480, so a photo that is not 4:3 has to be
    fitted somehow. Letterboxing is the honest choice: it never crops content away, and it
    makes the borders obviously "not part of the picture" rather than subtly wrong.

Usage
    python tools/make_frame.py photo.jpg
    python tools/make_frame.py photo.jpg --out frame.bin --fit crop --background 0
    python tools/make_frame.py --gradient demo.bin

    # then on the board
    python3 hdmi_show_image.py --raw frame.bin --preset document
"""

from __future__ import annotations

import argparse
import sys

import numpy as np

DEFAULT_WIDTH = 640
DEFAULT_HEIGHT = 480


def load_image(path: str) -> np.ndarray:
    from PIL import Image

    with Image.open(path) as img:
        return np.asarray(img.convert("RGB"), dtype=np.uint8)


def fit_frame(img: np.ndarray, width: int, height: int, mode: str,
              background: int) -> np.ndarray:
    from PIL import Image

    src = Image.fromarray(img)
    src_w, src_h = src.size
    scale = max(width / src_w, height / src_h) if mode == "crop" else min(width / src_w,
                                                                       height / src_h)
    new_w, new_h = max(1, round(src_w * scale)), max(1, round(src_h * scale))
    resized = src.resize((new_w, new_h), Image.LANCZOS)

    canvas = Image.new("RGB", (width, height), (background, background, background))
    canvas.paste(resized, ((width - new_w) // 2, (height - new_h) // 2))
    if mode == "crop":
        canvas = canvas.crop(((new_w - width) // 2 if new_w > width else 0,
                              (new_h - height) // 2 if new_h > height else 0,
                              (new_w - width) // 2 + width if new_w > width else width,
                              (new_h - height) // 2 + height if new_h > height else height))
    return np.asarray(canvas, dtype=np.uint8)


def gradient(width: int, height: int) -> np.ndarray:
    """A self-test frame: the same pattern the on-board demos use."""
    img = np.zeros((height, width, 3), dtype=np.uint8)
    ramp = np.linspace(20, 235, height, dtype=np.uint8).reshape(height, 1)
    img[:, :, 0] = ramp
    img[:, :, 1] = ramp
    img[:, :, 2] = ramp
    top = height // 2 - 60
    img[top:top + 120, :, :] = 128
    for row in range(top + 10, top + 110, 22):
        left = 40
        while left < width - 60:
            run = int(30 + (left * 7) % 90)
            img[row:row + 10, left:min(left + run, width - 40), :] = 25
            left += run + 18
    img[10:70, 10:130, 2] = 220
    img[10:70, 140:260, 1] = 220
    img[10:70, 270:390, 0] = 220
    return img


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("image", nargs="?", help="source picture (any format Pillow reads)")
    ap.add_argument("--gradient", metavar="OUT", help="write the built-in test frame instead")
    ap.add_argument("--out", default="frame.bin", help="output raw file (default frame.bin)")
    ap.add_argument("--width", type=int, default=DEFAULT_WIDTH)
    ap.add_argument("--height", type=int, default=DEFAULT_HEIGHT)
    ap.add_argument("--fit", choices=("letterbox", "crop"), default="letterbox",
                    help="how to handle a different aspect ratio (default letterbox)")
    ap.add_argument("--background", type=int, default=0,
                    help="letterbox colour, 0..255 (default 0 = black)")
    args = ap.parse_args(argv)

    if args.gradient:
        frame = gradient(args.width, args.height)
        args.out = args.gradient
    elif args.image:
        src = load_image(args.image)
        print(f"source {args.image}: {src.shape[1]}x{src.shape[0]}")
        frame = fit_frame(src, args.width, args.height, args.fit, args.background)
    else:
        ap.error("give an image, or --gradient OUT")
        return 2

    payload = frame.tobytes()
    with open(args.out, "wb") as fh:
        fh.write(payload)

    expected = args.width * args.height * 3
    status = "ok" if len(payload) == expected else "SIZE MISMATCH"
    print(f"wrote {args.out}: {len(payload)} bytes "
          f"({args.width}x{args.height}x3 = {expected}) - {status}")
    print(f"mean {frame.mean():.1f}, min {frame.min()}, max {frame.max()}")
    if len(payload) != expected:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
