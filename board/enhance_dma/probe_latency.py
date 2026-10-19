#!/usr/bin/env python3
"""Dump the latency GPIO's raw registers and its hwh connections."""

from __future__ import annotations

import numpy as np

REG_NAMES = {0x00: "GPIO_DATA(ch1)", 0x04: "GPIO_TRI(ch1)",
             0x08: "GPIO2_DATA(ch2)", 0x0C: "GPIO2_TRI(ch2)",
             0x10: "GIER", 0x14: "IP_ISR(ch1)", 0x18: "IP_IER(ch1)",
             0x1C: "IP_ISR(ch2)", 0x20: "IP_IER(ch2)"}


def main() -> int:
    from pynq import Overlay, allocate

    ol = Overlay("enhance_dma.bit")
    names = [n for n in ol.ip_dict if "gpio_lat" in n.lower()]
    print("gpio_lat instances:", names)
    if not names:
        return 1
    ip = getattr(ol, names[0])

    print("=== registers before any transfer ===")
    for off, name in REG_NAMES.items():
        print(f"  0x{off:02x} {name:<16} = 0x{ip.mmio.read(off):08x}")

    # push one frame so the monitor sees traffic
    dma = ol.axi_dma_0
    kern = getattr(ol, "enhance_0")
    w, h = 1280, 720
    src = allocate(shape=(w * h,), dtype=np.uint32)
    dst = allocate(shape=(w * h,), dtype=np.uint32)
    src[:] = ((np.arange(w * h, dtype=np.uint32) * 7) & 0x00FFFFFF)
    src.flush()
    dst.flush()

    kern.mmio.write(0x10, w * h)
    kern.mmio.write(0x18, w)
    for off, val in ((0x20, 16), (0x24, 255), (0x28, 16), (0x2C, 16),
                     (0x30, 0), (0x34, 0), (0x38, 0), (0x3C, 0), (0x40, 0)):
        kern.mmio.write(off, val)
    kern.mmio.write(0x00, 0x1)
    dma.sendchannel.transfer(src, start=0, nbytes=w * h * 4)
    dma.recvchannel.transfer(dst, start=0, nbytes=w * h * 4)
    dma.sendchannel.wait()
    dma.recvchannel.wait()
    print(f"kernel ctrl now 0x{kern.mmio.read(0x00):08x}")

    print("=== registers after one frame ===")
    for off, name in REG_NAMES.items():
        print(f"  0x{off:02x} {name:<16} = 0x{ip.mmio.read(off):08x}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
