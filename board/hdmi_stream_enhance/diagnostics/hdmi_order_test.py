#!/usr/bin/env python3
"""Which of the two orderings keeps the pixel stream alive?

Observed: hdmi_solid.py (configure, start, writeframe) returns in 3 ms, while a script that
writes a preset first then does the same thing blocks in the first writeframe forever.

This tests the four interesting positions of a configuration write relative to the output
path being up, each one timed, so the point where the stream stops can be named instead of
guessed.

    sudo python3 -u hdmi_order_test.py
"""

from __future__ import annotations

import signal
import time

import numpy as np

import hdmi_live as hl


class Timeout(Exception):
    pass


def _handler(signum, frame):        # noqa: ARG001
    raise Timeout()


def timed(label: str, func, seconds: int = 8):
    signal.alarm(seconds)
    t0 = time.monotonic()
    try:
        func()
        print(f"  OK      {label:<38} {(time.monotonic()-t0)*1000:7.1f} ms", flush=True)
        return True
    except Timeout:
        print(f"  BLOCKED {label:<38} > {seconds} s", flush=True)
        return False
    finally:
        signal.alarm(0)


def main() -> int:
    signal.signal(signal.SIGALRM, _handler)

    from pynq import Overlay
    from pynq.lib.video import VideoMode

    W, H = 640, 480
    ol = Overlay("enhance_hdmi.bit")
    out = ol.video.hdmi_out
    cfg = hl.find(ol, "gpio_enh_cfg")
    lat = hl.find(ol, "gpio_enh_lat")

    hpd = hl.find(ol, "gpio_hdmiin")
    if hpd is not None:
        hpd.mmio.write(0x00, 0x1)

    green = np.zeros((H, W, 3), dtype=np.uint8)
    green[:, :, 1] = 200

    print("A: output up first, then a frame", flush=True)
    out.configure(VideoMode(W, H, 24, 60))
    out.start()
    buf = out.newframe()
    buf[:] = green
    ok_a = timed("start -> writeframe", lambda: out.writeframe(buf))

    print("B: configuration write while streaming", flush=True)
    ok_b = timed("write_preset(pass)", lambda: hl.write_preset(cfg, "pass"))
    ok_b2 = timed("writeframe after config write", lambda: out.writeframe(buf))
    print(f"     latency now: {hl.read_latency(lat)}", flush=True)

    print("C: second configuration write", flush=True)
    ok_c = timed("write_preset(night)", lambda: hl.write_preset(cfg, "night"))
    ok_c2 = timed("writeframe after second write", lambda: out.writeframe(buf))

    print("D: configuration write before the output path comes up", flush=True)
    out.stop()
    ok_d0 = timed("write_preset(document)", lambda: hl.write_preset(cfg, "document"))
    out.configure(VideoMode(W, H, 24, 60))
    out.start()
    buf2 = out.newframe()
    buf2[:] = green
    ok_d = timed("writeframe after config-then-start", lambda: out.writeframe(buf2))

    print("\nsummary", flush=True)
    print(f"  A {ok_a}  B {ok_b and ok_b2}  C {ok_c and ok_c2}  D {ok_d0 and ok_d}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
