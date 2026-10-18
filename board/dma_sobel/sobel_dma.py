#!/usr/bin/env python3
"""DMA verification of the Sobel accelerator on PYNQ-Z2.

Runs on the board (Jupyter terminal or notebook). Sends a test frame through
the AXI DMA -> sobel_stream -> AXI DMA path, reads the result back out of DDR and
compares it bit-exactly against the golden reference produced on the host by
``sim/sobel/golden_sobel.py``.

Why one DMA transfer per row
    The kernel treats TLAST as end-of-line, exactly like PYNQ's pixel_pack on the
    HDMI path. A single transfer for the whole frame would therefore look like
    one 921600-pixel line. One transfer per row reproduces the HDMI stream
    behaviour, which is what we want to verify.

Why the third frame is the one compared
    The line buffers start at zero, so the first frame's top rows are garbage.
    By the third frame the buffers hold real data and the kernel is in its
    steady state, which is exactly what the ``--border wrap`` golden model
    describes.

Usage
    python3 sobel_dma.py                      # 3 frames, compare frame 3
    python3 sobel_dma.py --frames 5 --width 1280 --height 720
    python3 sobel_dma.py --no-compare         # throughput measurement only
"""

from __future__ import annotations

import argparse
import csv
import sys
import time

import numpy as np

try:
    from pynq import Overlay, allocate
except ImportError:  # allows --help and linting off-board
    Overlay = None
    allocate = None


def find_dma(ol):
    """Return a DMA driver for the axi_dma IP in this overlay.

    PYNQ versions differ: some bind ``pynq.lib.dma.DMA`` automatically, others
    hand back a bare ``DefaultIP`` that has ``mmio`` but no ``sendchannel``.
    Handle both instead of dying on a version difference.
    """
    for name, ip in ol.ip_dict.items():
        if "axi_dma" not in ip.get("type", "") and "axi_dma" not in name:
            continue
        dev = getattr(ol, name, None)
        if dev is not None and hasattr(dev, "sendchannel"):
            return dev
        from pynq.lib.dma import DMA
        return DMA(ol.ip_dict[name])
    raise RuntimeError(f"no AXI DMA in overlay; IPs are: {list(ol.ip_dict)}")


def pack_rgb(rgb: np.ndarray) -> np.ndarray:
    """HxWx3 uint8 -> flat uint32 words {R,G,B} in bits [23:0]."""
    r = rgb[:, :, 0].astype(np.uint32)
    g = rgb[:, :, 1].astype(np.uint32)
    b = rgb[:, :, 2].astype(np.uint32)
    return ((r << 16) | (g << 8) | b).reshape(-1)


def unpack_rgb(words: np.ndarray, width: int, height: int) -> np.ndarray:
    w = np.asarray(words, dtype=np.uint32).reshape(height, width)
    r = ((w >> 16) & 0xFF).astype(np.uint8)
    g = ((w >> 8) & 0xFF).astype(np.uint8)
    b = (w & 0xFF).astype(np.uint8)
    return np.dstack([r, g, b])


def _transfer(channel, buf, start_bytes: int, nbytes: int) -> None:
    """PYNQ 2.6+ takes start/nbytes; older versions need a buffer slice."""
    try:
        channel.transfer(buf, start=start_bytes, nbytes=nbytes)
    except TypeError:
        itemsize = buf.itemsize
        channel.transfer(buf[start_bytes // itemsize:(start_bytes + nbytes) // itemsize])


def run_frame(dma, in_buf, out_buf, width: int, height: int) -> float:
    """Push one frame row by row. Returns elapsed seconds."""
    row_bytes = width * 4
    in_buf.flush()
    t0 = time.perf_counter()
    for row in range(height):
        offset = row * row_bytes
        _transfer(dma.sendchannel, in_buf, offset, row_bytes)
        _transfer(dma.recvchannel, out_buf, offset, row_bytes)
        dma.sendchannel.wait()
        dma.recvchannel.wait()
    elapsed = time.perf_counter() - t0
    out_buf.invalidate()
    return elapsed


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bitstream", default="sobel_dma.bit")
    ap.add_argument("--input", default="test_720p.png")
    ap.add_argument("--reference", default="sobel_720p.png")
    ap.add_argument("--output", default="sobel_dma_out.png")
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=720)
    ap.add_argument("--frames", type=int, default=3)
    ap.add_argument("--no-compare", action="store_true")
    ap.add_argument("--metrics", default="metrics.csv")
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
    print(f"  DMA IP: {dma}")

    in_buf = allocate(shape=(w * h,), dtype=np.uint32)
    out_buf = allocate(shape=(w * h,), dtype=np.uint32)
    in_buf[:] = pack_rgb(rgb)

    times = []
    for f in range(args.frames):
        dt = run_frame(dma, in_buf, out_buf, w, h)
        times.append(dt)
        print(f"  frame {f + 1}/{args.frames}: {dt * 1000:.1f} ms "
              f"({w * h / dt / 1e6:.2f} Mpixel/s)")

    got = unpack_rgb(out_buf, w, h)
    Image.fromarray(got).save(args.output)
    print(f"wrote {args.output}")

    fps = args.frames / sum(times)
    mps = w * h * args.frames / sum(times) / 1e6
    print(f"throughput: {fps:.2f} frame/s, {mps:.2f} Mpixel/s")

    status = "measured"
    if not args.no_compare:
        ref = np.asarray(Image.open(args.reference).convert("RGB"))
        if ref.shape != got.shape:
            print(f"FAIL: reference shape {ref.shape} != output {got.shape}")
            return 1
        diff = np.abs(got.astype(np.int32) - ref.astype(np.int32))
        bad = int(np.count_nonzero(diff))
        print(f"mismatched channels: {bad} / {diff.size}, max |diff| = {int(diff.max())}")
        if bad == 0:
            print("COMPARE PASS (bit-exact)")
            status = "pass"
        else:
            yy, xx, cc = np.nonzero(diff)
            for k in range(min(5, len(yy))):
                print(f"  first diff: y={yy[k]} x={xx[k]} ch={cc[k]}")
            print("COMPARE FAIL")
            status = "fail"

    try:
        with open(args.metrics, "a", newline="") as fh:
            writer = csv.writer(fh)
            if fh.tell() == 0:
                writer.writerow(["timestamp", "width", "height", "frames",
                                 "total_s", "fps", "mpixel_s", "result"])
            writer.writerow([time.strftime("%Y-%m-%dT%H:%M:%S"), w, h, args.frames,
                             f"{sum(times):.6f}", f"{fps:.3f}", f"{mps:.3f}", status])
        print(f"appended to {args.metrics}")
    except OSError as exc:
        print(f"warning: could not write metrics: {exc}")

    return 0 if status in ("pass", "measured") else 1


if __name__ == "__main__":
    raise SystemExit(main())
