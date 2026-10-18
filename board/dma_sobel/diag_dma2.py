#!/usr/bin/env python3
"""Second-stage DMA diagnosis: is the kernel producing output at all?

diag_dma.py showed MM2S completing (DMASR=0x1002: IDLE|IOC) while S2MM sat at
0x0000 (started, never finished). Two very different causes look identical from
the outside:

  a) the kernel emits pixels but without TLAST -> S2MM waits forever after the
     right number of beats
  b) the kernel emits nothing at all -> S2MM waits forever with an empty buffer

Reading the destination buffer settles it: if it contains processed pixels, the
data path works and only the end-of-transfer marker is missing.

    sudo python3 diag_dma2.py
"""

from __future__ import annotations

import time

import numpy as np

MM2S_DMASR = 0x04
S2MM_DMASR = 0x34


def main() -> int:
    from pynq import Overlay, allocate

    width = 1280
    ol = Overlay("sobel_dma.bit")
    dma = ol.axi_dma_0

    src = allocate(shape=(width,), dtype=np.uint32)
    dst = allocate(shape=(width,), dtype=np.uint32)
    dst[:] = 0xDEADBEEF          # mark the buffer so untouched words are obvious
    # A recognisable gradient so processed output is distinguishable from input.
    src[:] = ((np.arange(width, dtype=np.uint32) * 3) & 0x00FFFFFF)
    src.flush()
    dst.flush()

    print(f"starting one row: {width} pixels, {width * 4} bytes")
    dma.sendchannel.transfer(src, start=0, nbytes=width * 4)
    dma.recvchannel.transfer(dst, start=0, nbytes=width * 4)

    for _ in range(20):
        time.sleep(0.1)
        if dma.sendchannel.idle and dma.recvchannel.idle:
            break

    send_idle = dma.sendchannel.idle
    recv_idle = dma.recvchannel.idle
    print(f"MM2S DMASR = 0x{dma.mmio.read(MM2S_DMASR):08x}  idle={send_idle}")
    print(f"S2MM DMASR = 0x{dma.mmio.read(S2MM_DMASR):08x}  idle={recv_idle}")

    dst.invalidate()
    words = np.asarray(dst)
    untouched = int(np.count_nonzero(words == 0xDEADBEEF))
    written = width - untouched

    print()
    print(f"destination words written by DMA : {written} / {width}")
    print(f"first 8 words                    : "
          f"{[hex(int(w)) for w in words[:8]]}")

    if written == 0:
        print()
        print("DIAGNOSIS: the kernel produced nothing.")
        print("  MM2S completed, so the kernel is clocked and consuming input,")
        print("  but no output beats reached the DMA. Look at the output stream")
        print("  wiring and at the kernel's TREADY/TVALID on s_out.")
        return 1

    print()
    print("DIAGNOSIS: the kernel IS producing pixels; only the end-of-transfer")
    print("  marker is missing, so S2MM never sees TLAST and waits forever.")
    print("  That is a TLAST problem, not a data problem: the fix is to give the")
    print("  DMA a TLAST it can trust (TLAST generator, or per-row transfers that")
    print("  the DMA itself terminates).")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
