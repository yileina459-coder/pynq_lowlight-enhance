#!/usr/bin/env python3
"""Offline test for board/dma_sobel/sobel_dma.py.

The board script cannot be tested on the host as-is: it imports ``pynq`` and
talks to a real AXI DMA. This test injects a fake ``pynq`` module whose DMA
reproduces the kernel's behaviour in numpy (same border policy, same line-buffer
warm-up), then runs the real board script end to end.

What it catches, before wasting a board round trip:
  * wrong packing/unpacking of {R,G,B} into 32-bit words
  * wrong row offsets in the per-row DMA transfers
  * comparing the wrong frame, or against the wrong reference policy
  * the metrics CSV writer

Run:  python sim/sobel/test_sobel_dma_offline.py
"""

from __future__ import annotations

import os
import sys

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "board", "dma_sobel"))
sys.path.insert(0, os.path.join(REPO, "sim", "sobel"))

import golden_sobel  # noqa: E402


# ---------------------------------------------------------------------------
# Fake PYNQ: just enough of the API for sobel_dma.py
# ---------------------------------------------------------------------------
class FakeBuffer:
    def __init__(self, n, dtype):
        self._a = np.zeros((n,), dtype=dtype)

    def __array__(self, dtype=None):
        return self._a if dtype is None else self._a.astype(dtype)

    def __getitem__(self, key):
        return self._a[key]

    def __setitem__(self, key, value):
        self._a[key] = value

    def __len__(self):
        return len(self._a)

    @property
    def itemsize(self):
        return self._a.itemsize

    def flush(self):
        pass

    def invalidate(self):
        pass


class FakeChannel:
    def __init__(self, dma, send: bool):
        self._dma = dma
        self._send = send
        self._pending = None

    def transfer(self, buf, start=0, nbytes=0):
        self._pending = (buf, int(start), int(nbytes))

    def wait(self):
        buf, start, nbytes = self._pending
        row = start // self._dma.row_bytes
        if self._send:
            self._dma.on_send(row, buf, start, nbytes)
        else:
            self._dma.on_recv(row, buf, start, nbytes)


class FakeDMA:
    """Reproduces sobel_stream's steady-state behaviour in numpy."""

    def __init__(self, width, height):
        self.w = width
        self.h = height
        self.row_bytes = width * 4
        self.rows = np.zeros((height, width), dtype=np.uint32)
        self.prev = [np.zeros(width, dtype=np.uint32), np.zeros(width, dtype=np.uint32)]
        self.sendchannel = FakeChannel(self, send=True)
        self.recvchannel = FakeChannel(self, send=False)

    @staticmethod
    def _luma(words: np.ndarray) -> np.ndarray:
        r = ((words >> 16) & 0xFF).astype(np.int32)
        g = ((words >> 8) & 0xFF).astype(np.int32)
        b = (words & 0xFF).astype(np.int32)
        return (77 * r + 150 * g + 29 * b) >> 8

    def on_send(self, row, buf, start, nbytes):
        words = np.asarray(buf)[start // 4:(start + nbytes) // 4]
        self.rows[row] = words

    def _row(self, index: int) -> np.ndarray:
        if index < 0:
            return self.prev[index + 2]
        return self.rows[index]

    def on_recv(self, row, buf, start, nbytes):
        top = self._luma(self._row(row - 2))
        mid = self._luma(self._row(row - 1))
        bot = self._luma(self._row(row))

        c0 = np.clip(np.arange(self.w) - 2, 0, None)
        c1 = np.clip(np.arange(self.w) - 1, 0, None)
        c2 = np.arange(self.w)

        gx = (top[c2] + 2 * mid[c2] + bot[c2]) - (top[c0] + 2 * mid[c0] + bot[c0])
        gy = (bot[c0] + 2 * bot[c1] + bot[c2]) - (top[c0] + 2 * top[c1] + top[c2])
        edge = np.clip(np.abs(gx) + np.abs(gy), 0, 255).astype(np.uint32)
        out = (edge << 16) | (edge << 8) | edge

        target = np.asarray(buf)
        target[start // 4:(start + nbytes) // 4] = out

        if row == self.h - 1:
            self.prev = [self.rows[self.h - 2].copy(), self.rows[self.h - 1].copy()]


class FakeOverlay:
    def __init__(self, path):
        self.path = path
        self.width = FAKE_W
        self.height = FAKE_H
        self.ip_dict = {"axi_dma_0": {"type": "xilinx.com:ip:axi_dma:7.1"}}
        self.axi_dma_0 = FakeDMA(FAKE_W, FAKE_H)


FAKE_W = 64
FAKE_H = 48


def make_fake_pynq():
    import types

    mod = types.ModuleType("pynq")
    mod.Overlay = FakeOverlay
    mod.allocate = lambda shape, dtype: FakeBuffer(shape[0], dtype)
    mod.__version__ = "fake"
    sys.modules["pynq"] = mod
    return mod


def main() -> int:
    from PIL import Image

    make_fake_pynq()
    import sobel_dma  # noqa: E402  (import after the fake module is installed)

    # Keep artefacts inside the repo: the sandbox (and CI) may not allow writes
    # to the system temp directory, and a fixed location is easier to inspect.
    tmp = os.path.join(REPO, ".tmp", "offline_test")
    os.makedirs(tmp, exist_ok=True)
    img = golden_sobel.make_test_image(FAKE_W, FAKE_H)
    in_path = os.path.join(tmp, "test.png")
    ref_path = os.path.join(tmp, "ref.png")
    out_path = os.path.join(tmp, "out.png")
    metrics = os.path.join(tmp, "metrics.csv")
    Image.fromarray(img).save(in_path)

    ref = golden_sobel.sobel(golden_sobel.luma(img), border="wrap")
    Image.fromarray(golden_sobel.to_rgb(ref)).save(ref_path)

    rc = sobel_dma.main([
        "--bitstream", os.path.join(tmp, "fake.bit"),
        "--input", in_path,
        "--reference", ref_path,
        "--output", out_path,
        "--width", str(FAKE_W),
        "--height", str(FAKE_H),
        "--frames", "3",
        "--metrics", metrics,
    ])

    ok = rc == 0
    if os.path.exists(out_path):
        got = np.asarray(Image.open(out_path).convert("RGB"))
        ok = ok and np.array_equal(got, golden_sobel.to_rgb(ref))
    else:
        ok = False

    ok = ok and os.path.exists(metrics)

    print("OFFLINE TEST PASS" if ok else "OFFLINE TEST FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
