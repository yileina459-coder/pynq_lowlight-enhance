#!/usr/bin/env python3
"""Find out exactly which output-path call blocks.

The image viewer hung between printing the picture statistics and reporting the preset, and it
hung with the verified bitstream as well, so the fault is in the script rather than in the
kernel. This walks the same steps with a print before and after each one and a watchdog
(signal.alarm) so a blocking call is reported instead of hanging the session.

    sudo python3 -u hdmi_image_debug.py --raw frame_photo.bin
"""

from __future__ import annotations

import argparse
import signal
import sys
import time

import numpy as np

import hdmi_live as hl


class Timeout(Exception):
    pass


def _handler(signum, frame):        # noqa: ARG001
    raise Timeout()


def step(label: str, func, seconds: int = 10):
    signal.alarm(seconds)
    started = time.monotonic()
    try:
        result = func()
        elapsed = (time.monotonic() - started) * 1000
        print(f"  OK   {label:<28} {elapsed:7.1f} ms -> {result}", flush=True)
        return result
    except Timeout:
        elapsed = (time.monotonic() - started) * 1000
        print(f"  BLOCKED {label:<25} still running after {elapsed:.0f} ms", flush=True)
        raise
    finally:
        signal.alarm(0)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bitstream", default="enhance_hdmi.bit")
    ap.add_argument("--raw", default="frame_photo.bin")
    ap.add_argument("--mode", default="640x480")
    args = ap.parse_args(argv)

    signal.signal(signal.SIGALRM, _handler)
    width, height = (int(v) for v in args.mode.lower().split("x"))

    from pynq import Overlay
    from pynq.lib.video import VideoMode

    step("Overlay()", lambda: type(Overlay(args.bitstream)).__name__)
    ol = Overlay(args.bitstream)
    out = ol.video.hdmi_out

    hpd = hl.find(ol, "gpio_hdmiin")
    cfg = hl.find(ol, "gpio_enh_cfg")
    lat = hl.find(ol, "gpio_enh_lat")
    print(f"  hpd={hpd is not None} cfg={cfg is not None} lat={lat is not None}", flush=True)

    if hpd is not None:
        step("hpd raise", lambda: hpd.mmio.write(0x00, 0x1))

    data = np.fromfile(args.raw, dtype=np.uint8)
    print(f"  raw bytes {data.size} ({width}x{height}x3 = {width*height*3})", flush=True)
    image = data.reshape(height, width, 3)

    step("write_preset(pass)", lambda: hl.write_preset(cfg, "pass"))
    step("configure", lambda: out.configure(VideoMode(width, height, 24, 60)))
    step("start", lambda: out.start())

    frame = step("newframe", lambda: out.newframe())
    step("assign pixels", lambda: frame.__setitem__(slice(None), image) or "ok")
    step("writeframe (1st)", lambda: out.writeframe(frame))
    step("writeframe (2nd)", lambda: out.writeframe(out.newframe().__class__()) if False
         else out.writeframe(frame))
    step("read_latency", lambda: hl.read_latency(lat))

    print("all steps completed", flush=True)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Timeout:
        print("stopped at the blocking step above", flush=True)
        sys.exit(1)
