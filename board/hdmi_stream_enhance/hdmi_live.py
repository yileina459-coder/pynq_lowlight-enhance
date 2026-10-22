#!/usr/bin/env python3
"""Live demo on real HDMI: apply presets and read the measured latency.

For the day the capture card is connected:

    HDMI source -> PYNQ HDMI IN -> enhance -> PYNQ HDMI OUT -> capture card -> PC

Nothing here reads pixels back: the pipeline deliberately bypasses the frame
buffer, so what you look at is the capture card's window on your PC. What this
script does is drive the kernel and report what the hardware says.

    # one preset, watch it on the capture card
    sudo python3 hdmi_live.py --preset document

    # cycle through presets every 4 s (nice for the demo video)
    sudo python3 hdmi_live.py --cycle 4

    # list the presets and exit
    python3 hdmi_live.py --list

Everything it prints comes from the hardware: the input mode from dvi2rgb, the
two cycle stamps from axis_cycle_stamp. If there is no source, it says so and
keeps waiting instead of pretending.
"""

from __future__ import annotations

import argparse
import sys
import time

# The 59 configuration bits, packed the way enh_cfg_split expects.
PRESETS = {
    # The tone curve is two-segment (below/above `knee`, with separate gains), so these numbers are
    # what decides "the picture got brighter". `clarity` adds local contrast.
    #
    # The first four are the honest "pass through" options; the rest trade clipping for visibility.
    # Values were chosen with tools/preview_enhance.py, which reimplements the kernel exactly:
    # 'bright' lifts a very dark picture (mean 33 -> 116) with under 3% blown highlights, while an
    # aggressive curve (gain_lo 64+) reaches 129 but blows ~39% of the frame, which is why it is
    # not the default.
    "pass":     dict(clarity=16, knee=255, gain_lo=16, gain_hi=16),
    "clarity":  dict(clarity=28, knee=255, gain_lo=16, gain_hi=16),
    "bright":   dict(clarity=24, knee=192, gain_lo=56, gain_hi=20),
    "night":    dict(clarity=28, knee=224, gain_lo=72, gain_hi=24),
    "document": dict(clarity=20, knee=192, gain_lo=64, gain_hi=16),
    "reading":  dict(clarity=24, knee=48, gain_lo=88, gain_hi=14),
    "invert":   dict(clarity=24, knee=192, gain_lo=56, gain_hi=20, invert=1, mono=1),
    "binarize": dict(clarity=16, knee=64, gain_lo=112, gain_hi=8,
                     thresh=112, binarize=1, mono=1),
    "split":    dict(clarity=28, knee=90, gain_lo=40, gain_hi=12, split_x=320),
}

GPIO_DATA, GPIO_TRI, GPIO2_DATA, GPIO2_TRI = 0x00, 0x04, 0x08, 0x0C


def pack(cfg: dict) -> tuple[int, int]:
    lo = ((cfg.get("clarity", 16) & 0xFF)
          | ((cfg.get("knee", 255) & 0xFF) << 8)
          | ((cfg.get("gain_lo", 16) & 0xFF) << 16)
          | ((cfg.get("gain_hi", 16) & 0xFF) << 24))
    hi = ((cfg.get("thresh", 0) & 0xFF)
          | ((cfg.get("binarize", 0) & 1) << 8)
          | ((cfg.get("invert", 0) & 1) << 9)
          | ((cfg.get("mono", 0) & 1) << 10)
          | ((cfg.get("split_x", 0) & 0xFFFF) << 11))
    return lo, hi


def find(ol, fragment: str):
    for name in ol.ip_dict:
        if fragment in name.lower():
            dev = getattr(ol, name, None)
            if dev is not None and hasattr(dev, "mmio"):
                return dev
    return None


# -----------------------------------------------------------------------------
# Hot-plug lines
#
# Both HPD GPIOs power up with *both* channels tri-stated (the direction register reads
# 0xFFFFFFFF), so the board never actually drives those pins. Writing the data register alone
# does nothing electrically - the direction register has to be cleared first.
#
# This matters on the output side: with HPD floating, a USB capture dongle cannot see that a
# source is present, keeps its HDMI receiver disabled, and shows its own internal test pattern.
# The symptom is indistinguishable from "the board is not producing video" even though the
# pipeline is running and the pixel clock is locked - it cost an hour of looking at the wrong
# end of a cable.
# -----------------------------------------------------------------------------

GPIO_DIR = 0x04          # channel 1 tri-state register: 0 = drive the pin


def _drive_hpd(dev, value: int = 1) -> None:
    """Turn channel 1 of an AXI GPIO into an output and drive it to ``value``."""
    dev.mmio.write(GPIO_DIR, 0x00000000)     # 0 = output
    dev.mmio.write(GPIO_DATA, value)


def raise_output_hpd(ol) -> bool:
    """Assert HPD towards the sink (the monitor or capture dongle)."""
    dev = find(ol, "hpd_video")
    if dev is None:
        return False
    _drive_hpd(dev, 1)
    return True


def raise_input_hpd(ol) -> bool:
    """Assert HPD towards the video source on the input side."""
    dev = find(ol, "gpio_hdmiin")
    if dev is None:
        return False
    _drive_hpd(dev, 1)
    return True


def hold_output_hpd_low(ol) -> bool:
    """Pull HPD low, as a cable being unplugged would."""
    dev = find(ol, "hpd_video")
    if dev is None:
        return False
    _drive_hpd(dev, 0)
    return True


def release_output_hpd(ol) -> bool:
    """Release HPD high, as a cable being plugged back in would."""
    dev = find(ol, "hpd_video")
    if dev is None:
        return False
    _drive_hpd(dev, 1)
    return True


def kick_output_hpd(ol, pause: float = 0.35) -> bool:
    """A low-then-high HPD pulse, for callers that cannot order it around other work."""
    if not hold_output_hpd_low(ol):
        return False
    time.sleep(pause)
    return release_output_hpd(ol)


def start_output(ol, out, width: int, height: int, fps: int = 60,
                 force: bool = False, verbose: bool = True):
    """Start the HDMI output exactly the way PYNQ expects, and nothing else.

    This is deliberately the plain sequence: program the mode (which sets both the pixel clock
    and the timing generator), start the VDMA, and let the caller fill the frame buffers.

    Two "improvements" were tried here and both are gone, because pictures stopped appearing
    after they were added:

      * skipping the mode programming when the read-back mode already matched, to avoid the
        brief TMDS interruption a clock reprogramming causes. It leaves the pixel clock in
        whatever state the previous session left it - and the read-back only proves what the
        VTC holds, not what the clock is doing.
      * pulsing HPD low and releasing it around the start, to imitate a cable replug. The sink
        does not like HPD being pulled while TMDS is running, and a capture dongle that ends up
        in that state shows its own pattern until a real replug.

    The measured facts that do hold: the output HPD GPIO is C_ALL_OUTPUTS on channel 1 and a
    read-only input on channel 2 (which reported 0 while the sink was unhappy), and a physical
    cable replug is the only thing that reliably recovers the dongle. So the demo rule is:
    start this once and do not restart it; tune parameters through files instead
    (see hdmi_resident.py).

    ``force`` is accepted for compatibility with callers and now has no effect.
    """
    from pynq.lib.video import VideoMode

    mode = VideoMode(width, height, 24, fps)
    out.configure(mode)
    out.start()
    if verbose:
        print(f"output {width}x{height}@{fps}: mode programmed, VDMA started", flush=True)
    return False


def roll_frame(picture, offset: int):
    """Shift a frame horizontally by ``offset`` pixels, wrapping around.

    A streaming pipeline in front of a video timing generator delays the pixels but not the
    timing: the output core opens its active window on schedule, so the content appears shifted
    left by the pipeline's latency in pixels and the left edge reappears on the right.

    Measured on this design: 41-46 pixels, which matches the kernel's 21-25 cycle latency plus
    roughly 20 pixels of timestamp/unpack/FIFO delay. Because the shift is in the picture the
    sink receives, compensating here fixes both a capture card and a real monitor.

    The value is measured, not guessed - tools/measure_capture_offset.py cross-correlates a
    capture against the reference card.
    """
    import numpy as np

    return np.roll(picture, offset, axis=1)


def open_overlay(bitstream: str = "enhance_hdmi.bit", verbose: bool = True):
    """Load an overlay and assert both hot-plug lines.

    Every load reprograms the PL, which resets the HPD GPIOs back to all-inputs. Writing the
    data register without clearing the direction register does nothing, so the sink sees a
    floating hot-plug line, a capture dongle keeps its receiver off, and the screen shows the
    dongle's own test pattern - indistinguishable from "the board is not producing video".

    Loading through this helper makes that step impossible to forget.
    """
    from pynq import Overlay

    ol = Overlay(bitstream)
    did_in = raise_input_hpd(ol)
    did_out = raise_output_hpd(ol)
    if verbose:
        print(f"loaded {bitstream}; HPD in={did_in} out={did_out}", flush=True)
    return ol


RST_BIT = 1 << 31          # bit 31 of word 1 asks the kernel to reset

# Set this to True only for the old port-configured bitstream.
#
# The memory-configured kernel (enhance_stream_cfg, used from 2026-10-22 on) reads all nine
# parameters from a BRAM word on every pixel, so a preset change takes effect on the next
# pixel and no reset is needed at all. Pulsing the reset would only interrupt the pixel
# stream and make the video-output core underflow - the fault that took a whole evening to
# pin down.
PULSE_RESET = False


def write_preset(cfg_ip, name: str) -> tuple[int, int]:
    """Write a preset. With the memory-configured kernel this is a plain register write.

    History worth keeping: with the kernel's configuration on plain input ports, HLS sampled
    it once in the pipeline prologue (the netlist contained
    ``binarize_read_reg_1446 <= binarize;``), so six of the nine parameters froze at
    power-up and a preset change required resetting the kernel to re-run that prologue.
    Resetting interrupted the pixel stream, so the output path had to be rebuilt after every
    switch. Moving the configuration into memory removed the whole chain of consequences.
    """
    lo, hi = pack(PRESETS[name])
    cfg_ip.mmio.write(GPIO_DATA, lo)
    if not PULSE_RESET:
        # Live path: one write, effective on the next pixel, nothing is interrupted.
        cfg_ip.mmio.write(GPIO2_DATA, hi)
        time.sleep(0.001)
    else:
        cfg_ip.mmio.write(GPIO2_DATA, hi | RST_BIT)  # remaining ones + reset asserted
        time.sleep(0.002)                            # let the reset settle
        cfg_ip.mmio.write(GPIO2_DATA, hi)            # release: prologue re-samples
        time.sleep(0.002)

    rb = (cfg_ip.mmio.read(GPIO_DATA), cfg_ip.mmio.read(GPIO2_DATA))
    if rb != (lo, hi):
        print(f"  WARNING: config readback {rb[0]:#010x},{rb[1]:#010x} "
              f"!= written {lo:#010x},{hi:#010x}")
    return lo, hi


SOF_ENABLE_BIT = 1 << 30     # spare bit in gpio_enh_cfg channel 2, wired to sof_gen_enable


def set_sof_enable(cfg_ip, enable: bool, preset: str | None = None) -> int:
    """Turn the generated SOF on or off without rebuilding anything.

    The bit is deliberately outside the configuration the kernel consumes (thresh/binarize/
    invert/mono/split_x occupy bits 0..26, bit 31 is the kernel reset request), so toggling it
    never disturbs a preset. It exists so the SOF path can be compared against the passthrough
    behaviour in one bitstream - each rebuild costs about 35 minutes.
    """
    # Read-modify-write so only bit 30 changes: the other bits carry the preset and the kernel
    # reset request, and rewriting them from a freshly packed preset would be redundant at best.
    hi = cfg_ip.mmio.read(GPIO2_DATA) & 0xFFFFFFFF
    if enable:
        hi |= SOF_ENABLE_BIT
    else:
        hi &= ~SOF_ENABLE_BIT & 0xFFFFFFFF
    cfg_ip.mmio.write(GPIO2_DATA, hi)
    return hi


def read_latency(lat_ip) -> tuple[int, int] | None:
    a, b = lat_ip.mmio.read(GPIO_DATA), lat_ip.mmio.read(GPIO2_DATA)
    if a == 0 and b == 0:
        return None
    return (b - a) & 0xFFFFFFFF


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bitstream", default="enhance_hdmi.bit")
    ap.add_argument("--preset", default="document", choices=sorted(PRESETS))
    ap.add_argument("--cycle", type=float, default=0.0,
                    help="seconds per preset; 0 = stay on --preset")
    ap.add_argument("--order", default="pass,clarity,document,night,invert,binarize,split",
                    help="preset order used by --cycle")
    ap.add_argument("--clock-mhz", type=float, default=142.857,
                    help="pixel-domain clock of the kernel (clk_142M)")
    ap.add_argument("--seconds", type=float, default=0.0,
                    help="stop after this many seconds (0 = run until Ctrl-C)")
    ap.add_argument("--wait-source", type=float, default=20.0,
                    help="how long to wait for an HDMI input mode before warning")
    ap.add_argument("--list", action="store_true", help="print presets and exit")
    args = ap.parse_args(argv)

    if args.list:
        for name, cfg in PRESETS.items():
            print(f"  {name:<9} {cfg}")
        return 0

    from pynq import Overlay

    print(f"loading {args.bitstream} ...")
    ol = Overlay(args.bitstream)
    if not hasattr(ol, "video"):
        print("FAIL: pynq.lib.video did not bind")
        return 1
    video = ol.video

    cfg_ip = find(ol, "gpio_enh_cfg")
    lat_ip = find(ol, "gpio_enh_lat")
    if cfg_ip is None or lat_ip is None:
        print("FAIL: configuration or latency GPIO missing from the overlay")
        return 1

    # This low-latency design bypasses the input VDMA, so inspect the HDMI frontend
    # directly instead of the unconfigured VDMA mode exposed by hdmi_in.mode.
    frontend = video.hdmi_in._hdmi
    deadline = time.monotonic() + args.wait_source
    try:
        frontend.start(init_timeout=max(1, int(args.wait_source)))
        mode = frontend.mode
    except Exception as exc:                          # noqa: BLE001
        print(f"HDMI input frontend did not lock: {type(exc).__name__}: {exc}")
        mode = None
    while mode is None and time.monotonic() < deadline:
        time.sleep(0.5)
        try:
            mode = frontend.mode
        except Exception:
            mode = None
    if mode is None:
        print("no HDMI input detected yet - check that the source is powered and")
        print("set to a mode the PYNQ-Z2 can lock (1280x720 is the safe one).")
        print("continuing anyway; the picture will appear when the source locks.")
    else:
        print(f"input detected: {mode.width}x{mode.height} @{mode.frame_rate} Hz")

    order = [p.strip() for p in args.order.split(",") if p.strip() in PRESETS]
    start = time.monotonic()
    preset = args.preset
    try:
        while True:
            for name in (order if args.cycle > 0 else [preset]):
                lo, hi = write_preset(cfg_ip, name)
                stamp = time.strftime("%H:%M:%S")
                print(f"[{stamp}] preset {name:<9} cfg=0x{lo:08x} 0x{hi:08x}")
                lat = read_latency(lat_ip)
                if lat is None:
                    print("           latency: not measured yet (no pixels have "
                          "passed since the PL was configured)")
                else:
                    print(f"           latency: {lat} pixel clocks "
                          f"(~{lat / args.clock_mhz:.3f} us at {args.clock_mhz} MHz)")
                if args.cycle > 0:
                    time.sleep(args.cycle)
                if args.seconds and (time.monotonic() - start) > args.seconds:
                    raise KeyboardInterrupt
            if args.cycle <= 0:
                # stay on the single preset and report the stamps once a second
                while True:
                    time.sleep(1.0)
                    lat = read_latency(lat_ip)
                    if lat is not None:
                        print(f"           latency: {lat} pixel clocks "
                              f"(~{lat / args.clock_mhz:.3f} us)")
                    if args.seconds and (time.monotonic() - start) > args.seconds:
                        raise KeyboardInterrupt
    except KeyboardInterrupt:
        print("stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
