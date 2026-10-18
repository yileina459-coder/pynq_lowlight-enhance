#!/usr/bin/env python3
"""Reusable AXI-DMA transfer helpers for PYNQ overlays.

Why this exists
    Every PYNQ + DMA project writes the same three fragile things by hand:
    finding the DMA instance (the attribute name differs per overlay), getting
    cache maintenance right (a missed ``flush`` produces stale data that looks
    like a logic bug), and waiting for completion without hanging forever when
    the stream stalls. This module packages those three, with a timeout that
    tells you *where* it stopped instead of freezing the notebook.

Usage (on the board)
    from pynq import Overlay, allocate
    from dma_stream import find_dma, transfer_rows

    ol = Overlay("design.bit")
    dma = find_dma(ol)
    src = allocate(shape=(n,), dtype=np.uint32)
    dst = allocate(shape=(n,), dtype=np.uint32)
    src[:] = data
    elapsed = transfer_rows(dma, src, dst, width=1280, height=720)

Notes
    * ``transfer_rows`` exists because many streaming kernels treat TLAST as
      end-of-line; the easy mistake is to send the whole frame as one transfer
      and wonder why only the first row looks right.
    * ``transfer_block`` is for kernels that only care about the end of the
      buffer, and is much faster (one transfer instead of ``height``).
"""

from __future__ import annotations

import time


def find_dma(overlay):
    """Return a DMA driver for the axi_dma IP in this overlay.

    PYNQ versions differ: some bind ``pynq.lib.dma.DMA`` automatically, others
    hand back a bare ``DefaultIP`` that has ``mmio`` but no ``sendchannel``.
    """
    for name, ip in overlay.ip_dict.items():
        if "axi_dma" not in ip.get("type", "") and "axi_dma" not in name:
            continue
        dev = getattr(overlay, name, None)
        if dev is not None and hasattr(dev, "sendchannel"):
            return dev
        from pynq.lib.dma import DMA
        return DMA(overlay.ip_dict[name])
    raise RuntimeError(f"no AXI DMA in overlay; IPs are: {list(overlay.ip_dict)}")


def _wait(channel, timeout: float, what: str) -> None:
    """Wait for a DMA channel, raising TimeoutError with context if it stalls."""
    deadline = time.monotonic() + timeout
    if hasattr(channel, "idle"):
        while not channel.idle:
            if time.monotonic() > deadline:
                raise TimeoutError(f"{what} did not complete within {timeout:.1f}s")
            time.sleep(0.0001)
    else:  # older PYNQ without the idle property
        channel.wait()


def _transfer(channel, buf, start_bytes: int, nbytes: int) -> None:
    """PYNQ 2.6+ takes start/nbytes; older versions need a buffer slice."""
    try:
        channel.transfer(buf, start=start_bytes, nbytes=nbytes)
    except TypeError:
        itemsize = buf.itemsize
        channel.transfer(buf[start_bytes // itemsize:(start_bytes + nbytes) // itemsize])


def transfer_rows(dma, src, dst, width: int, height: int,
                  timeout: float = 5.0, pixel_bytes: int = 4) -> float:
    """Send one row per DMA transfer; returns elapsed seconds.

    Use this when the kernel uses TLAST as end-of-line (the usual case for video
    operators). ``pixel_bytes`` is 4 for a 32-bit AXI-Stream, 3 for 24-bit.
    """
    row_bytes = width * pixel_bytes
    src.flush()
    t0 = time.perf_counter()
    for row in range(height):
        offset = row * row_bytes
        _transfer(dma.sendchannel, src, offset, row_bytes)
        _transfer(dma.recvchannel, dst, offset, row_bytes)
        _wait(dma.sendchannel, timeout, "MM2S")
        _wait(dma.recvchannel, timeout, "S2MM")
    elapsed = time.perf_counter() - t0
    dst.invalidate()
    return elapsed


def transfer_block(dma, src, dst, nbytes: int, timeout: float = 5.0) -> float:
    """Send the whole buffer as one transfer; returns elapsed seconds."""
    src.flush()
    t0 = time.perf_counter()
    _transfer(dma.sendchannel, src, 0, nbytes)
    _transfer(dma.recvchannel, dst, 0, nbytes)
    _wait(dma.sendchannel, timeout, "MM2S")
    _wait(dma.recvchannel, timeout, "S2MM")
    elapsed = time.perf_counter() - t0
    dst.invalidate()
    return elapsed
