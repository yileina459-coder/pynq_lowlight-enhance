#!/usr/bin/env python3
"""Run the enhance kernel on the board over AXI-DMA and compare bit-exactly.

Why this exists before the HDMI capture card arrives
    The capture card is only needed to *see* the picture. The kernel itself can be
    proven now: push a frame through it over DMA, read the result back, and compare
    it with the numpy golden model channel by channel. Zero tolerance - the same
    standard used for the Sobel path.

What it proves
    1. the bounded enhance kernel produces exactly the golden pixels, for every
       preset, through real hardware;
    2. the 59 configuration bits are actually reaching the datapath (each preset
       disagrees with the others, so a stuck register would show up);
    3. the DMA framing works with a configurable kernel (whole-frame transfer).

Usage (on the board, as root, with the PYNQ venv)
    sudo env XILINX_XRT=/usr PATH=/usr/local/share/pynq-venv/bin:/usr/bin:/bin \\
        HOME=/root /usr/local/share/pynq-venv/bin/python3 enhance_dma.py

    python3 enhance_dma.py --input test_dim_720p.png --presets pass,reading
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
import time

import numpy as np

try:
    from pynq import Overlay, allocate
except ImportError:  # allows --help and linting off-board
    Overlay = None
    allocate = None

HERE = os.path.dirname(os.path.abspath(__file__))

# The golden model lives in the repository layout; on the board the two files are
# copied next to this script under sim/. Try both so the same file works in-repo
# and on the board.
for candidate in (
    os.path.join(HERE, "sim", "enhance"),
    os.path.join(HERE, "..", "..", "sim", "enhance"),
    os.path.join(HERE, "..", "sim", "enhance"),
):
    if os.path.isdir(candidate):
        sys.path.insert(0, candidate)
        break

import golden_enhance as golden  # noqa: E402

# AXI-Lite registers of enhance_bounded(), in C argument order.
#
# The offsets are NOT hard-coded: HLS 2026.1 spaced these scalars 8 bytes apart
# (0x10, 0x18, 0x20, ...), not the 4-byte packing one might assume, so they are
# read out of the overlay's own register map at run time. The first version of
# this script assumed 4-byte spacing and the mismatch check caught it before a
# single register was written - which is exactly what that check is for.
REG_NAMES = [
    "n_pixels", "line_width",
    "clarity", "knee", "gain_lo", "gain_hi", "thresh",
    "binarize", "invert", "mono", "split_x",
]
CTRL = "ctrl"

# Which presets to run by default: every distinct code path, in a fixed order.
DEFAULT_PRESETS = ["pass", "clarity", "reading", "night", "invert", "binarize", "split"]


def find_dma(ol):
    """Return a DMA driver for the axi_dma IP, tolerating PYNQ version differences."""
    for name, ip in ol.ip_dict.items():
        if "axi_dma" not in ip.get("type", "") and "axi_dma" not in name:
            continue
        dev = getattr(ol, name, None)
        if dev is not None and hasattr(dev, "sendchannel"):
            return dev
        from pynq.lib.dma import DMA
        return DMA(ol.ip_dict[name])
    raise RuntimeError(f"no AXI DMA in overlay; IPs are: {list(ol.ip_dict)}")


def find_kernel(ol):
    """Return (name, IP) for the enhance kernel's AXI-Lite control."""
    for name, ip in ol.ip_dict.items():
        if "enhance" not in name.lower():
            continue
        dev = getattr(ol, name, None)
        if dev is not None and hasattr(dev, "mmio"):
            return name, dev
    raise RuntimeError(f"no enhance kernel with registers; IPs are: {list(ol.ip_dict)}")


def resolve_regs(ol, name: str) -> dict:
    """Read the AXI-Lite offsets out of the overlay, so the script cannot drift.

    Returns {register name: byte offset}, including 'ctrl'. Raises if any
    expected register is absent - a kernel built without a scalar (or with the
    scalar optimised away) must fail here rather than silently write into a
    neighbouring register.
    """
    regs = ol.ip_dict[name].get("registers", {})
    table = {}
    for key in [CTRL] + REG_NAMES:
        source = "CTRL" if key == CTRL else key
        if source not in regs:
            raise RuntimeError(
                f"register {key!r} missing from the overlay; "
                f"the map has: {sorted(regs)}")
        table[key] = int(regs[source]["address_offset"])
    spacing = sorted(table[k] for k in REG_NAMES)
    print(f"  register map of {name}: OK ({len(table)} registers, "
          f"scalars at 0x{spacing[0]:x}..0x{spacing[-1]:x})")
    return table


def preset_to_regs(preset: str, width: int) -> dict:
    """Translate a named preset into register values, mirroring golden.render()."""
    cfg = dict(golden.PRESETS[preset])
    split = cfg.pop("split", False)
    regs = {
        "clarity": cfg.get("clarity", 16),
        "knee": cfg.get("knee", 255),
        "gain_lo": cfg.get("gain_lo", 16),
        "gain_hi": cfg.get("gain_hi", 16),
        "thresh": cfg.get("thresh", 0),
        "binarize": 1 if cfg.get("binarize", False) else 0,
        "invert": 1 if cfg.get("invert", False) else 0,
        "mono": 1 if cfg.get("mono", False) else 0,
        "split_x": min(320, width // 2) if split else 0,
    }
    return regs


def pack_rgb(rgb: np.ndarray) -> np.ndarray:
    r = rgb[:, :, 0].astype(np.uint32)
    g = rgb[:, :, 1].astype(np.uint32)
    b = rgb[:, :, 2].astype(np.uint32)
    return ((r << 16) | (g << 8) | b).reshape(-1)


def unpack_rgb(words: np.ndarray, width: int, height: int) -> np.ndarray:
    w = np.asarray(words, dtype=np.uint32).reshape(height, width)
    return np.dstack([((w >> 16) & 0xFF).astype(np.uint8),
                      ((w >> 8) & 0xFF).astype(np.uint8),
                      (w & 0xFF).astype(np.uint8)])


def _transfer(channel, buf, nbytes: int) -> None:
    try:
        channel.transfer(buf, start=0, nbytes=nbytes)
    except TypeError:
        channel.transfer(buf[: nbytes // buf.itemsize])


def run_preset(dma, kern, in_buf, out_buf, width: int, height: int, regs: dict,
               offsets: dict) -> float:
    """One whole-frame pass. Returns elapsed seconds."""
    n = width * height
    kern.mmio.write(offsets["n_pixels"], n)
    kern.mmio.write(offsets["line_width"], width)
    for key in REG_NAMES[2:]:
        kern.mmio.write(offsets[key], int(regs[key]))
    kern.mmio.write(offsets[CTRL], 0x1)          # ap_start

    t0 = time.perf_counter()
    _transfer(dma.sendchannel, in_buf, n * 4)
    _transfer(dma.recvchannel, out_buf, n * 4)
    dma.sendchannel.wait()
    dma.recvchannel.wait()

    deadline = time.monotonic() + 5.0
    while not (kern.mmio.read(offsets[CTRL]) & 0x2):
        if time.monotonic() > deadline:
            raise TimeoutError("kernel ap_done did not rise")
        time.sleep(0.0002)
    elapsed = time.perf_counter() - t0
    out_buf.invalidate()
    return elapsed


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bitstream", default="enhance_dma.bit")
    ap.add_argument("--input", default="test_dim_720p.png")
    ap.add_argument("--presets", default=",".join(DEFAULT_PRESETS))
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=720)
    ap.add_argument("--frames", type=int, default=3, help="timed repetitions per preset")
    ap.add_argument("--border", default="wrap", choices=["wrap", "replicate"],
                    help="vertical border the golden model should assume; the "
                         "hardware keeps the previous frame lines in its buffers, "
                         "which is wrap semantics (same convention as the Sobel "
                         "reference images)")
    ap.add_argument("--outdir", default="", help="write per-preset output images here")
    ap.add_argument("--metrics", default="metrics_enhance.csv")
    args = ap.parse_args(argv)

    if Overlay is None:
        print("This script must run on the PYNQ board (pynq package not found).")
        return 2

    from PIL import Image

    w, h = args.width, args.height
    rgb = np.asarray(Image.open(args.input).convert("RGB"))
    if rgb.shape[0] != h or rgb.shape[1] != w:
        print(f"FAIL: input is {rgb.shape[1]}x{rgb.shape[0]}, expected {w}x{h}")
        return 1

    print(f"loading overlay {args.bitstream}")
    ol = Overlay(args.bitstream)
    dma = find_dma(ol)
    name, kern = find_kernel(ol)
    print(f"  DMA IP: {dma}")
    print(f"  kernel: {name}")
    offsets = resolve_regs(ol, name)

    in_buf = allocate(shape=(w * h,), dtype=np.uint32)
    out_buf = allocate(shape=(w * h,), dtype=np.uint32)
    in_buf[:] = pack_rgb(rgb)
    in_buf.flush()

    presets = [p.strip() for p in args.presets.split(",") if p.strip()]
    rows = []
    failures = 0
    outputs = {}

    for preset in presets:
        regs = preset_to_regs(preset, w)
        expected = golden.render(rgb, preset, args.border)

        times = []
        for _ in range(max(1, args.frames)):
            times.append(run_preset(dma, kern, in_buf, out_buf, w, h, regs, offsets))
        got = unpack_rgb(out_buf, w, h)
        outputs[preset] = got

        diff = np.abs(got.astype(np.int32) - expected.astype(np.int32))
        mismatched = int(np.count_nonzero(diff))
        total = int(diff.size)
        best = min(times) * 1000.0
        print(f"  {preset:<9} {best:7.1f} ms   mismatched {mismatched}/{total}"
              f"   max|diff| {int(diff.max())}")
        if mismatched:
            failures += 1
            ys, xs, cs = np.nonzero(diff)
            i = 0
            print(f"    first mismatch at (row {ys[i]}, col {xs[i]}, channel {cs[i]}):"
                  f" got {got[ys[i], xs[i], cs[i]]}, expected {expected[ys[i], xs[i], cs[i]]}")
        rows.append(dict(preset=preset, frame_ms=round(best, 2),
                         mismatched=mismatched, channels=total,
                         result="pass" if mismatched == 0 else "fail",
                         **regs))

    if args.outdir:
        os.makedirs(args.outdir, exist_ok=True)
        for preset, img in outputs.items():
            Image.fromarray(img).save(os.path.join(args.outdir, f"enhance_{preset}.png"))
        before_after = np.hstack([rgb, np.full((h, 4, 3), 255, dtype=np.uint8),
                                  outputs.get("reading", rgb)])
        Image.fromarray(before_after).save(os.path.join(args.outdir, "enhance_montage.png"))
        print(f"wrote images to {args.outdir}")

    if rows:
        exists = os.path.exists(args.metrics)
        with open(args.metrics, "a", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
            if not exists:
                writer.writeheader()
            writer.writerows(rows)
        print(f"appended to {args.metrics}")

    print()
    if failures:
        print(f"COMPARE FAIL: {failures} preset(s) differ from the golden model")
        return 1
    print("COMPARE PASS (bit-exact) for all presets")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
