#!/usr/bin/env python3
"""Third-stage diagnosis: how many beats does the kernel actually emit?

The previous run showed 1264 of 1280 destination words written while the S2MM
never completed. Two explanations fit:

  * the DMA holds the last partial burst until the transfer is closed by TLAST,
    so 1280 beats arrived but only 1264 reached memory
  * the kernel genuinely stopped 16 beats short

Running several transfer sizes separates them: the tail explanation always loses
a fixed burst (16 words on a 32-bit stream), the other scales with the row.

Each case reloads the overlay, so a stuck channel from the previous case cannot
poison the next one (reprogramming the DMA behind PYNQ's back makes the driver
refuse to start it).

    sudo python3 diag_dma3.py
"""

from __future__ import annotations

import time

import numpy as np

SENTINEL = 0xDEADBEEF


def run_case(bitfile: str, words: int) -> tuple[int, bool]:
    from pynq import Overlay, allocate

    ol = Overlay(bitfile)          # fresh PL configuration for every case
    dma = ol.axi_dma_0

    src = allocate(shape=(words,), dtype=np.uint32)
    dst = allocate(shape=(words,), dtype=np.uint32)
    dst[:] = SENTINEL
    src[:] = ((np.arange(words, dtype=np.uint32) * 5) & 0x00FFFFFF)
    src.flush()
    dst.flush()

    nbytes = words * 4
    dma.sendchannel.transfer(src, start=0, nbytes=nbytes)
    dma.recvchannel.transfer(dst, start=0, nbytes=nbytes)

    for _ in range(30):
        time.sleep(0.1)
        if dma.sendchannel.idle and dma.recvchannel.idle:
            break

    done = bool(dma.recvchannel.idle)
    dst.invalidate()
    written = int(np.count_nonzero(np.asarray(dst) != SENTINEL))
    return written, done


def main() -> int:
    bitfile = "sobel_dma.bit"
    print(f"{'words':>6} {'bytes':>7} {'written':>8} {'short by':>9}  s2mm_done")
    results = []
    for words in (8, 16, 32, 64, 256, 1280):
        written, done = run_case(bitfile, words)
        results.append((words, written, done))
        print(f"{words:>6} {words * 4:>7} {written:>8} {words - written:>9}  {done}")

    print()
    ok = [r for r in results if r[2]]
    bad = [r for r in results if not r[2]]
    if not bad:
        print("DIAGNOSIS: every transfer completed on its own.")
        return 0

    shorts = [w - wr for w, wr, d in bad]
    if max(shorts) <= 16:
        print("DIAGNOSIS: the incomplete transfers are always short by <=16 words and")
        print("  never finish -> the DMA is waiting for a TLAST that never arrives.")
        print("  The data itself is fine (it reaches memory), only the terminator is")
        print("  missing.")
        return 2

    print("DIAGNOSIS: the shortfall scales with the transfer, so the kernel is not")
    print("  emitting every beat. Look at the kernel's output handshake.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
