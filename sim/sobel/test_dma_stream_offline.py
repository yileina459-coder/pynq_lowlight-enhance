#!/usr/bin/env python3
"""Offline test for skill/dma_stream.

Two things are checked:
  1. transfer_rows drives the numpy fake DMA end to end and the result matches
     the golden reference (this is the path the board script uses);
  2. transfer_block issues exactly one transfer per channel with the right byte
     count (the fake DMA only models per-row transfers, so this part uses a
     recording stub instead).

Run:  python sim/sobel/test_dma_stream_offline.py
"""

from __future__ import annotations

import os
import sys

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "sim", "sobel"))
sys.path.insert(0, os.path.join(REPO, "sim", "common"))
sys.path.insert(0, os.path.join(REPO, "skill", "dma_stream"))

import image_ops  # noqa: E402
from test_sobel_dma_offline import FakeBuffer, FakeDMA  # noqa: E402
from dma_stream import find_dma, transfer_block, transfer_rows  # noqa: E402

W, H, FRAMES = 64, 48, 3


class RecordingChannel:
    def __init__(self):
        self.calls = []
        self.idle = True

    def transfer(self, buf, start=0, nbytes=0):
        self.calls.append((int(start), int(nbytes)))

    def wait(self):
        pass


class RecordingDMA:
    def __init__(self):
        self.sendchannel = RecordingChannel()
        self.recvchannel = RecordingChannel()


class MiniOverlay:
    """Just enough of the Overlay API for find_dma()."""

    def __init__(self, dma):
        self.ip_dict = {"axi_dma_0": {"type": "xilinx.com:ip:axi_dma:7.1"}}
        self.axi_dma_0 = dma


def main() -> int:
    ok = True

    # --- 1. per-row transfers, checked against the golden model -------------
    dma = FakeDMA(W, H)
    src = FakeBuffer(W * H, np.uint32)
    dst = FakeBuffer(W * H, np.uint32)

    img = image_ops.make_test_image(W, H)
    words = ((img[:, :, 0].astype(np.uint32) << 16) |
             (img[:, :, 1].astype(np.uint32) << 8) |
             img[:, :, 2].astype(np.uint32)).reshape(-1)
    src[:] = words

    for _ in range(FRAMES):
        transfer_rows(dma, src, dst, width=W, height=H)

    got = np.asarray(dst).reshape(H, W)
    got_rgb = np.dstack([((got >> 16) & 0xFF).astype(np.uint8),
                         ((got >> 8) & 0xFF).astype(np.uint8),
                         (got & 0xFF).astype(np.uint8)])
    ref = image_ops.to_rgb(image_ops.sobel(image_ops.luma(img), border="wrap"))
    rows_ok = np.array_equal(got_rgb, ref)
    print(f"transfer_rows matches golden: {rows_ok}")
    ok = ok and rows_ok

    # --- 2. whole-buffer transfer: one call per channel --------------------
    rec = RecordingDMA()
    found = find_dma(MiniOverlay(rec))
    buf_src = FakeBuffer(W * H, np.uint32)
    buf_dst = FakeBuffer(W * H, np.uint32)
    transfer_block(found, buf_src, buf_dst, nbytes=W * H * 4, timeout=1.0)

    exp = [(0, W * H * 4)]
    block_ok = rec.sendchannel.calls == exp and rec.recvchannel.calls == exp
    print(f"transfer_block call pattern: send={rec.sendchannel.calls} "
          f"recv={rec.recvchannel.calls} -> {block_ok}")
    ok = ok and block_ok

    print("DMA STREAM TEST PASS" if ok else "DMA STREAM TEST FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
