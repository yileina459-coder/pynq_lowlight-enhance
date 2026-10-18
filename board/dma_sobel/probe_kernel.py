#!/usr/bin/env python3
"""Probe the bounded kernel's register map and try a single row.

Printed first, before any transfer, so the offsets are known even if the transfer
misbehaves.
"""

from __future__ import annotations

import time

import numpy as np

SENTINEL = 0xDEADBEEF
W = 1280


def main() -> int:
    from pynq import Overlay, allocate

    ol = Overlay("sobel_dma.bit")

    print("=== IPs ===")
    for name, ip in ol.ip_dict.items():
        print(f"  {name}: {ip.get('type')}")

    print("=== sobel_0 registers ===")
    info = ol.ip_dict.get("sobel_0", {})
    regs = info.get("registers", {})
    for reg, props in regs.items():
        print(f"  {reg}: offset=0x{props.get('address_offset', 0):x} "
              f"type={props.get('type')}")

    kern = getattr(ol, "sobel_0", None)
    print(f"kernel object: {kern}")
    if kern is None:
        return 1

    ctrl = 0x00
    nreg = 0x10
    print(f"before start: CTRL=0x{kern.mmio.read(ctrl):08x} "
          f"N@0x10=0x{kern.mmio.read(nreg):08x} "
          f"N@0x18=0x{kern.mmio.read(0x18):08x}")

    dma = ol.axi_dma_0
    src = allocate(shape=(W,), dtype=np.uint32)
    dst = allocate(shape=(W,), dtype=np.uint32)
    dst[:] = SENTINEL
    src[:] = ((np.arange(W, dtype=np.uint32) * 5) & 0x00FFFFFF)
    src.flush()
    dst.flush()

    kern.mmio.write(nreg, W)
    kern.mmio.write(ctrl, 0x1)          # ap_start
    print(f"after start:  CTRL=0x{kern.mmio.read(ctrl):08x}")

    dma.sendchannel.transfer(src, start=0, nbytes=W * 4)
    dma.recvchannel.transfer(dst, start=0, nbytes=W * 4)

    for _ in range(20):
        time.sleep(0.1)
        if dma.sendchannel.idle and dma.recvchannel.idle:
            break

    print(f"after 2 s:    CTRL=0x{kern.mmio.read(ctrl):08x} "
          f"MM2S idle={dma.sendchannel.idle} S2MM idle={dma.recvchannel.idle}")
    dst.invalidate()
    written = int(np.count_nonzero(np.asarray(dst) != SENTINEL))
    print(f"destination words written: {written} / {W}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
