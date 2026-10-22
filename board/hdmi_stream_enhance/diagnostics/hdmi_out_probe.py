#!/usr/bin/env python3
"""Read the output side's registers while a demo keeps running.

Why pure MMIO
    Loading the overlay from a second process is safe only if PYNQ skips the download, and
    instantiating the video hierarchy would touch the VDMA that the running demo owns. Reading a
    few registers through pynq.MMIO at addresses taken from the .hwh disturbs nothing, which
    means the diagnosis can happen *while* the demo is live - exactly when the fault is visible.

What each reading means
    hpd_video    an AXI GPIO whose channel 1 drives the HPD line towards the sink and whose
                 channel 2 reads it back. Direction register all-ones = still an input, i.e. the
                 board is not driving the line at all.
    axi_dynclk   0x00 control (bit 0 = run), 0x04 status (bit 0 = locked), 0x08/0x0C pixel clock
                 in Hz as a 64-bit little-endian pair.
    vtc_out      the timing generator: 0x00..0x0C are the active size, then the porch registers.
                 A frame width of zero means the generator is not programmed, which happens when
                 the pixel clock never got configured.

    python3 hdmi_out_probe.py
"""

from __future__ import annotations

from pynq import MMIO

HPD = 0x41230000
DYNCLK = 0x43C10000
VTC = 0x43C20000


def words(base: int, count: int) -> list[int]:
    dev = MMIO(base, 0x1000)
    return [dev.read(4 * i) for i in range(count)]


def main() -> int:
    print("hdmi_out_hpd_video @ 0x%08x" % HPD)
    hpd = MMIO(HPD, 0x1000)
    ch1_data, ch1_tri = hpd.read(0x00), hpd.read(0x04)
    ch2_data, ch2_tri = hpd.read(0x08), hpd.read(0x0C)
    print(f"  ch1 data=0x{ch1_data:08x} tri=0x{ch1_tri:08x} "
          f"({'driven' if (ch1_tri & 1) == 0 else 'INPUT (tri-stated)'})")
    print(f"  ch2 data=0x{ch2_data:08x} tri=0x{ch2_tri:08x} "
          f"({'reads the line' if (ch2_tri & 1) else 'also driving'})")
    print(f"  -> HPD level seen on the line: {ch2_data & 1}")

    print("axi_dynclk @ 0x%08x" % DYNCLK)
    clk = MMIO(DYNCLK, 0x1000)
    control, status = clk.read(0x00), clk.read(0x04)
    lsw, msw = clk.read(0x08), clk.read(0x0C)
    freq = (msw << 32) | lsw
    print(f"  control=0x{control:08x} (run={control & 1})")
    print(f"  status =0x{status:08x} (locked={status & 1})")
    print(f"  pixel clock = {freq} Hz raw  (LSW=0x{lsw:08x} MSW=0x{msw:08x})")
    if 20_000_000 < freq < 200_000_000:
        print(f"               = {freq / 1e6:.3f} MHz")

    print("vtc_out @ 0x%08x" % VTC)
    v = words(VTC, 12)
    print("  regs:", " ".join(f"{w:08x}" for w in v))
    if v[0] or v[1]:
        print(f"  active size reads {v[0] + 1}x{v[1] + 1} (registers are size-1)")

    problems = []
    if (ch1_tri & 1):
        problems.append("HPD is still an input - the board is not driving it")
    if not (status & 1):
        problems.append("pixel clock is not locked")
    if v[0] == 0 or v[1] == 0:
        problems.append("timing generator reports zero active size")

    print()
    if problems:
        print("PROBLEMS:")
        for p in problems:
            print("  -", p)
    else:
        print("no obvious fault in these registers: HPD is driven, the clock is locked "
              "and the timing generator is programmed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
