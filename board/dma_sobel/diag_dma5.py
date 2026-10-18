#!/usr/bin/env python3
"""Does the TLAST generator fire at all?

If the kernel emits slightly fewer beats than it receives (its pipeline may not
drain at the end of a transfer), a 1280-beat transfer never gives the generator
its 1280th beat and the S2MM never completes. Sending two rows in ONE transfer
separates the two cases: a working generator fires on beat 1280 - in the middle
of the transfer - and the S2MM completes early.

Each case reloads the overlay so a stuck channel cannot poison the next one.
"""

from __future__ import annotations

import time

import numpy as np

SENTINEL = 0xDEADBEEF


def run_case(bitfile: str, words: int) -> tuple[int, bool]:
    from pynq import Overlay, allocate

    ol = Overlay(bitfile)
    dma = ol.axi_dma_0

    src = allocate(shape=(words,), dtype=np.uint32)
    dst = allocate(shape=(words,), dtype=np.uint32)
    dst[:] = SENTINEL
    src[:] = ((np.arange(words, dtype=np.uint32) * 5) & 0x00FFFFFF)
    src.flush()
    dst.flush()

    dma.sendchannel.transfer(src, start=0, nbytes=words * 4)
    dma.recvchannel.transfer(dst, start=0, nbytes=words * 4)
    for _ in range(20):
        time.sleep(0.1)
        if dma.sendchannel.idle and dma.recvchannel.idle:
            break

    done = bool(dma.recvchannel.idle)
    dst.invalidate()
    written = int(np.count_nonzero(np.asarray(dst) != SENTINEL))
    return written, done


def main() -> int:
    for words in (1280, 2560, 3840):
        written, done = run_case("sobel_dma.bit", words)
        print(f"{words:>5} words -> written {written:>5}, s2mm_done={done}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
