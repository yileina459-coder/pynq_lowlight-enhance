#!/usr/bin/env python3
"""Fourth-stage diagnosis: is the kernel's output bit-aligned with the golden model?

The size sweep showed every transfer losing exactly one AXI burst (16 words) and
never completing, which means the DMA is waiting for TLAST. Before fixing that,
this checks the other half: are the beats that *do* arrive correct and in the
right order? If one beat were dropped, every pixel after it would shift and the
comparison below would fail at the first edge.

Method: a 4-row image where every row is identical. Vertical neighbours are then
the same value, so the expected Sobel output is a pure horizontal derivative and
can be computed exactly with numpy - no border-policy ambiguity.

    sudo python3 diag_dma4.py
"""

from __future__ import annotations

import time

import numpy as np

SENTINEL = 0xDEADBEEF
W = 1280
ROWS = 4


def golden_row(colour: np.ndarray) -> np.ndarray:
    """Sobel of one row when its vertical neighbours are identical."""
    r = colour[:, 0].astype(np.int32)
    g = colour[:, 1].astype(np.int32)
    b = colour[:, 2].astype(np.int32)
    y = (77 * r + 150 * g + 29 * b) >> 8

    idx_c0 = np.clip(np.arange(W) - 2, 0, None)
    idx_c1 = np.clip(np.arange(W) - 1, 0, None)
    idx_c2 = np.arange(W)

    row = y                                     # top == mid == bot
    gx = (row[idx_c2] + 2 * row[idx_c2] + row[idx_c2]) - \
         (row[idx_c0] + 2 * row[idx_c0] + row[idx_c0])
    gy = 0
    mag = np.clip(np.abs(gx) + np.abs(gy), 0, 255)
    return (mag << 16 | mag << 8 | mag).astype(np.uint32)


def main() -> int:
    from pynq import Overlay, allocate

    # One row of black with a bright 5-pixel block: exactly one strong edge pair.
    colour = np.zeros((W, 3), dtype=np.uint8)
    colour[98:103] = 255
    expected = golden_row(colour)
    words = (colour[:, 0].astype(np.uint32) << 16) | \
            (colour[:, 1].astype(np.uint32) << 8) | \
            colour[:, 2].astype(np.uint32)

    ol = Overlay("sobel_dma.bit")
    dma = ol.axi_dma_0
    src = allocate(shape=(W,), dtype=np.uint32)
    dst = allocate(shape=(W,), dtype=np.uint32)
    src[:] = words
    src.flush()

    for row in range(ROWS):
        dst[:] = SENTINEL
        dst.flush()
        src.flush()
        dma.sendchannel.transfer(src, start=0, nbytes=W * 4)
        dma.recvchannel.transfer(dst, start=0, nbytes=W * 4)
        for _ in range(10):
            time.sleep(0.1)
            if dma.sendchannel.idle and dma.recvchannel.idle:
                break
        dst.invalidate()
        got = np.asarray(dst).copy()
        written = int(np.count_nonzero(got != SENTINEL))
        print(f"row {row}: {written} words written, "
              f"expected non-zero at 99..101 -> {[hex(int(got[c])) for c in (97, 98, 99, 100, 101, 102, 103)]}")

    got = np.asarray(dst).copy()
    valid = min(written, W - 16)                 # ignore the un-flushed tail burst
    mismatches = np.nonzero(got[:valid] != expected[:valid])[0]
    print()
    print(f"compared first {valid} words against the golden model")
    print(f"mismatches: {len(mismatches)}")
    if len(mismatches):
        first = int(mismatches[0])
        print(f"  first mismatch at column {first}: got {hex(int(got[first]))} "
              f"expected {hex(int(expected[first]))}")
        print()
        print("DIAGNOSIS: the output is not aligned with the golden model, so the")
        print("  kernel is dropping or duplicating beats, not just the TLAST.")
        return 1

    print()
    print("DIAGNOSIS: every beat that arrives is bit-correct and in order.")
    print("  The kernel's data path is fine; only the end-of-transfer marker is")
    print("  missing. Fixing TLAST is therefore an integration fix, not a kernel fix.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
