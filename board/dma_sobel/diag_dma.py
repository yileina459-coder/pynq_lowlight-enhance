#!/usr/bin/env python3
"""Diagnose a DMA path that loads but does not move data.

Run this when ``sobel_dma.py`` prints the overlay and the DMA object and then
sits there: it separates the three ways that can happen.

    python3 diag_dma.py

What it tells you
    * ``MM2S_DMASR`` / ``S2MM_DMASR`` before anything is started. Bit 0 is
      Halted: if the channel reports Halted after a start request, the IP is
      being held in reset or has no clock.
    * whether the MM2S channel starts at all (Halted clears) when 2 rows are
      pushed. If it stays halted, the problem is the DMA/reset side.
    * whether the S2MM channel finishes. If MM2S completes but S2MM never does,
      the kernel is not producing output (or not producing TLAST), which points
      at the kernel's clock/reset or at the stream wiring.

Nothing is written to the board's filesystem, and the buffers are small (2 rows).
"""

from __future__ import annotations

import sys
import time

import numpy as np

REG = {
    "MM2S_DMACR": 0x00,
    "MM2S_DMASR": 0x04,
    "MM2S_SA": 0x18,
    "MM2S_LENGTH": 0x28,
    "S2MM_DMACR": 0x30,
    "S2MM_DMASR": 0x34,
    "S2MM_DA": 0x48,
    "S2MM_LENGTH": 0x58,
}

HALTED = 1 << 0
IDLE = 1 << 1
IOC_IRQ = 1 << 12
ERR_IRQ = 1 << 14


def flags(value: int) -> str:
    names = []
    if value & HALTED:
        names.append("HALTED")
    if value & IDLE:
        names.append("IDLE")
    if value & IOC_IRQ:
        names.append("IOC")
    if value & ERR_IRQ:
        names.append("ERR")
    return "|".join(names) if names else "-"


def dump(dma, label: str) -> None:
    print(f"[{label}]")
    for name in ("MM2S_DMASR", "S2MM_DMASR", "MM2S_DMACR", "S2MM_DMACR"):
        try:
            v = dma.mmio.read(REG[name])
            extra = f"  ({flags(v)})" if name.endswith("DMASR") else ""
            print(f"  {name:<12} 0x{v:08x}{extra}")
        except Exception as exc:  # pragma: no cover - board only
            print(f"  {name:<12} read failed: {exc}")


def main() -> int:
    from pynq import Overlay, allocate

    width = 1280
    rows = 2
    n = width * rows
    row_bytes = width * 4

    print("loading overlay sobel_dma.bit")
    ol = Overlay("sobel_dma.bit")
    dma = ol.axi_dma_0

    dump(dma, "before start")

    src = allocate(shape=(n,), dtype=np.uint32)
    dst = allocate(shape=(n,), dtype=np.uint32)
    pattern = ((np.arange(n, dtype=np.uint32) * 7) & 0x00FFFFFF)
    src[:] = pattern
    src.flush()

    print(f"\nstarting one {row_bytes}-byte transfer (row 0)")
    dma.sendchannel.transfer(src, start=0, nbytes=row_bytes)
    dma.recvchannel.transfer(dst, start=0, nbytes=row_bytes)

    send_done = recv_done = False
    for elapsed_ms in range(0, 2000, 100):
        time.sleep(0.1)
        send_done = dma.sendchannel.idle
        recv_done = dma.recvchannel.idle
        if send_done and recv_done:
            break

    dump(dma, f"after {elapsed_ms + 100} ms")

    print()
    print(f"MM2S finished: {send_done}")
    print(f"S2MM finished: {recv_done}")

    if not send_done and not recv_done:
        print("\nDIAGNOSIS: neither channel moved. The DMA is not running.")
        print("  Most likely: the design's reset is still asserted, or the PL clock")
        print("  is not toggling. Nothing the PS can do in software fixes this; the")
        print("  overlay needs a rebuild with the reset properly released.")
        return 1

    if send_done and not recv_done:
        print("\nDIAGNOSIS: MM2S sent the data but the result never came back.")
        print("  The kernel is consuming input but not producing output, so check")
        print("  the kernel's clock/reset, and whether TLAST reaches S2MM.")
        return 2

    if send_done and recv_done:
        got = np.asarray(dst)[:width]
        print("\nDIAGNOSIS: one row moved end to end - the path works.")
        print(f"  first 8 output words: {[hex(int(w)) for w in got[:8]]}")
        print("  If sobel_dma.py still stalls, the problem is in the per-frame loop")
        print("  (transfer size or offset), not in the hardware path.")
        return 0

    print("\nOdd state, please report the register dump above.")
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
