#!/usr/bin/env python3
"""A narrated walk-through of the enhancement pipeline, for judging and for demos.

Why a separate script
    Flipping through eight presets every few seconds is fine for a recording, but it is a poor
    way to *judge* the pipeline: the eye needs a moment on each state, and it needs to know what
    the state is supposed to demonstrate. This script holds each preset for a fixed time and
    prints, in step with the screen, what to look at and what the expected change is.

    It uses one picture on purpose - the standard test card drawn at the panel's native size -
    so that every difference on screen is caused by the processing and nothing else.

    sudo python3 -u hdmi_tour.py --image testcard_640x480.png --hold 20
"""

from __future__ import annotations

import argparse
import time

import numpy as np

import hdmi_live as hl

# (preset, what the operator should look at)
TOUR = [
    ("pass",
     "baseline - the card as drawn: title, three body sizes, chips, dark page, ramp, stripes"),
    ("clarity",
     "edge enhancement - the one-pixel stripes gain halos, the small text gets crisper"),
    ("reading",
     "shadows lifted - the dark page starts to show its faint text, polarity unchanged"),
    ("document",
     "stronger lift with the knee higher - small text on the light page is easiest here"),
    ("night",
     "maximum lift - the whole frame brightens, highlights may start to clip"),
    ("invert",
     "polarity flipped - the light page goes dark, which some viewers prefer for text"),
    ("binarize",
     "hard threshold - only black and white remain; strokes either survive or vanish"),
    ("split",
     "split screen - left third untouched, right side processed, boundary at x=213"),
]


def load_picture(args, width: int, height: int) -> np.ndarray:
    if args.raw:
        data = np.fromfile(args.raw, dtype=np.uint8)
        expected = width * height * 3
        if data.size != expected:
            raise SystemExit(f"{args.raw}: {data.size} bytes, expected {expected}")
        return data.reshape(height, width, 3)

    from PIL import Image

    with Image.open(args.image) as img:
        img = img.convert("RGB")
        if img.size == (width, height):
            print(f"picture {args.image}: {width}x{height}, used at native size",
                  flush=True)
            return np.asarray(img, dtype=np.uint8)
        scale = min(width / img.width, height / img.height)
        size = (max(1, round(img.width * scale)), max(1, round(img.height * scale)))
        resized = img.resize(size, Image.LANCZOS)
        canvas = Image.new("RGB", (width, height), (0, 0, 0))
        canvas.paste(resized, ((width - size[0]) // 2, (height - size[1]) // 2))
        print(f"picture {args.image}: {img.width}x{img.height} -> {size[0]}x{size[1]} "
              f"centred (letterboxed)", flush=True)
        return np.asarray(canvas, dtype=np.uint8)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bitstream", default="enhance_hdmi.bit")
    ap.add_argument("--mode", default="640x480")
    ap.add_argument("--image", default="testcard_640x480.png")
    ap.add_argument("--raw", default=None)
    ap.add_argument("--roll", type=int, default=0,
                    help="shift the picture right by N pixels to compensate the "
                         "pipeline latency (measured 41-46 on this design)")
    ap.add_argument("--hold", type=float, default=20.0, help="seconds per state")
    ap.add_argument("--rounds", type=int, default=0,
                    help="how many times to walk the list (0 = until Ctrl-C)")
    args = ap.parse_args(argv)

    from pynq.lib.video import VideoMode

    width, height = (int(v) for v in args.mode.lower().split("x"))

    ol = hl.open_overlay(args.bitstream)
    out = ol.video.hdmi_out
    cfg = hl.find(ol, "gpio_enh_cfg")
    lat = hl.find(ol, "gpio_enh_lat")
    if cfg is None:
        raise SystemExit("gpio_enh_cfg not found - wrong bitstream?")

    picture = load_picture(args, width, height)
    if args.roll:
        picture = hl.roll_frame(picture, args.roll)
        print(f"picture rolled right by {args.roll} px to compensate the pipeline latency",
              flush=True)
    print(f"frame mean {picture.mean():.1f}", flush=True)

    hl.start_output(ol, out, width, height)
    for _ in range(4):
        buf = out.newframe()
        buf[:] = picture
        out.writeframe(buf)

    total = len(TOUR) * args.hold
    label = f"{args.rounds} round(s)" if args.rounds else "until Ctrl-C"
    print(f"\n=== guided tour: {len(TOUR)} states, {args.hold:.0f} s each, {label} ===\n",
          flush=True)

    readings = []
    done = 0
    while args.rounds == 0 or done < args.rounds:
        done += 1
        for index, (name, description) in enumerate(TOUR, 1):
            hl.write_preset(cfg, name)
            time.sleep(0.2)
            n = hl.read_latency(lat)
            readings.append((name, n))
            print(f"[{done}.{index}/{len(TOUR)}] {name.upper():<9} "
                  f"({time.strftime('%H:%M:%S')})", flush=True)
            print(f"      look for: {description}", flush=True)
            print(f"      latency reading: {n}", flush=True)
            time.sleep(args.hold)

    print("\n=== summary ===", flush=True)
    for name, n in readings:
        print(f"  {name:<9} latency {n}", flush=True)
    print("\ntour finished; the picture stays on the last state until this process exits",
          flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
