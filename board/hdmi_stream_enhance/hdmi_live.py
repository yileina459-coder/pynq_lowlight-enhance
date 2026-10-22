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
    "pass":     dict(clarity=16, knee=255, gain_lo=16, gain_hi=16),
    "clarity":  dict(clarity=28, knee=255, gain_lo=16, gain_hi=16),
    "reading":  dict(clarity=24, knee=48, gain_lo=88, gain_hi=14),
    "document": dict(clarity=20, knee=192, gain_lo=64, gain_hi=12),
    "night":    dict(clarity=30, knee=36, gain_lo=120, gain_hi=10),
    "invert":   dict(clarity=24, knee=48, gain_lo=88, gain_hi=14, invert=1, mono=1),
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


def kick_output_hpd(ol, pause: float = 0.25) -> bool:
    """Toggle the output hot-plug line low then high.

    A sink samples HPD at connect time and re-reads EDID when it sees a low-to-high transition.
    Several USB capture dongles do not re-lock their HDMI receiver when the source simply starts
    streaming again after an interruption - they keep showing their own pattern until the cable
    is re-plugged. Driving HPD low for a moment and releasing it produces the same edge in
    software, which is what makes a demo recoverable without touching the hardware.
    """
    dev = find(ol, "hpd_video")
    if dev is None:
        return False
    _drive_hpd(dev, 1)
    time.sleep(0.05)
    _drive_hpd(dev, 0)
    time.sleep(pause)
    _drive_hpd(dev, 1)
    return True


def _clock_locked(ol) -> bool:
    """True if the pixel-clock MMCM/PLL reports locked."""
    dev = find(ol, "dynclk")
    if dev is None:
        return False
    return bool(dev.mmio.read(0x04) & 0x1)


def start_output(ol, out, width: int, height: int, fps: int = 60,
                 force: bool = False, verbose: bool = True):
    """Bring the HDMI output up without needlessly reprogramming the pixel clock.

    Why this exists
        VideoOut.configure() assigns ``self._hdmi.mode``, and that setter calls
        ``_display.mode(...)``, which reprograms axi_dynclk. Reprogramming drops TMDS for a
        moment, and a USB capture dongle does not always re-lock afterwards - it then keeps
        showing its own test pattern while the board streams perfectly. writeframe() still
        returns quickly and the latency counter still updates, because the break is in the
        clock/serialiser domain, not in the pixel path.

    How the mode is checked
        The frontend's ``mode`` *getter* reads the frame size back from the VTC
        (``frame_width()``/``frame_height()``), so the hardware's current mode can be queried
        without any side effect. If it already matches and the clock is locked, the clock is
        left alone and only the VDMA and the timing generator are (re)started.

    What must not be skipped
        ``_hdmi.start()`` enables the video timing generator. Leaving it out (an earlier
        version of this function did) means the VDMA is configured but nothing consumes frames,
        and writeframe() blocks forever - the fix has to keep that call.
    """
    from pynq.lib.video import VideoMode

    mode = VideoMode(width, height, 24, fps)

    current = None
    try:
        current = out._hdmi.mode
        current_px = (current.width, current.height)
    except Exception:                                  # noqa: BLE001
        current_px = None

    reuse = (not force) and current_px == (width, height) and _clock_locked(ol)

    if reuse:
        out._vdma.writechannel.stop()
        out._hdmi.start()                 # timing generator on, clock untouched
        out._vdma.writechannel.mode = mode
        out.start()
        if verbose:
            print(f"output {width}x{height}@{fps}: pixel clock already correct "
                  f"({current_px[0]}x{current_px[1]} locked), left untouched", flush=True)
    else:
        out.configure(mode)
        out.start()
        if verbose:
            print(f"output {width}x{height}@{fps}: pixel clock programmed", flush=True)
    return reuse


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
    # Always give the sink a hot-plug edge at start-up. A dongle that missed the previous
    # re-lock keeps showing its own pattern no matter how good the signal is, and it only
    # recovers on a low-to-high transition - which is why re-plugging the cable 'fixes' it.
    # Doing it here means every run begins from a defined sink state instead of inheriting
    # whatever the last run left behind.
    kicked = kick_output_hpd(ol) if did_out else False
    if verbose:
        print(f"loaded {bitstream}; HPD in={did_in} out={did_out} edge={kicked}", flush=True)
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
