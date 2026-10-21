#!/usr/bin/env python3
"""Prove that a preset change no longer interrupts the pixel stream.

What "no glitch" means as a measurement
    The old sequence reset the kernel on every switch. That stalled the AXI-Stream, the
    video-output core underflowed, and the output path had to be rebuilt - which is what the
    black flash on every switch was.

    With the configuration in memory the kernel is never reset, so the stream should not
    pause at all. That is testable without watching a screen: keep writing frames while
    switching presets and time every write. writeframe() only returns once the VDMA has
    completed a frame, so a stalled stream shows up as a long write. Any write over the
    threshold is reported with the preset that was active.

    It also samples the pipeline latency counter around each switch, which must stay at 21 -
    a restarted pipeline would report a different value or none at all.

    sudo python3 -u hdmi_stream_enhance_live_check.py --cycle 5 --total 60
"""

from __future__ import annotations

import argparse
import statistics
import time

import numpy as np

import hdmi_live as hl

ORDER = ["pass", "clarity", "reading", "document", "night", "invert", "binarize", "split"]
SLOW_MS = 60.0          # a healthy write is ~5-20 ms; anything above this is a stall


def test_image(width: int, height: int) -> np.ndarray:
    img = np.zeros((height, width, 3), dtype=np.uint8)
    ramp = np.linspace(20, 235, height, dtype=np.uint8).reshape(height, 1)
    img[:, :, 0] = ramp
    img[:, :, 1] = ramp
    img[:, :, 2] = ramp
    top = height // 2 - 60
    img[top:top + 120, :, :] = 128
    for row in range(top + 10, top + 110, 22):
        left = 40
        while left < width - 60:
            run = int(30 + (left * 7) % 90)
            img[row:row + 10, left:min(left + run, width - 40), :] = 25
            left += run + 18
    img[10:70, 10:130, 2] = 220
    img[10:70, 140:260, 1] = 220
    img[10:70, 270:390, 0] = 220
    return img


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bitstream", default="enhance_hdmi.bit")
    ap.add_argument("--mode", default="640x480")
    ap.add_argument("--cycle", type=float, default=5.0, help="seconds per preset")
    ap.add_argument("--total", type=float, default=60.0, help="run length in seconds")
    args = ap.parse_args(argv)

    from pynq import Overlay
    from pynq.lib.video import VideoMode

    width, height = (int(v) for v in args.mode.lower().split("x"))

    print(f"loading {args.bitstream}", flush=True)
    ol = Overlay(args.bitstream)
    out = ol.video.hdmi_out

    hpd = hl.find(ol, "gpio_hdmiin")
    if hpd is not None:
        hpd.mmio.write(0x00, 0x1)
    cfg = hl.find(ol, "gpio_enh_cfg")
    lat = hl.find(ol, "gpio_enh_lat")

    image = test_image(width, height)

    out.configure(VideoMode(width, height, 24, 60))
    out.start()
    # newframe() only exists once configure()/start() have built the VDMA frame cache.
    buf = out.newframe()
    buf[:] = image
    for _ in range(4):
        out.writeframe(buf)
    print("output path up; every following write is timed", flush=True)

    hl.write_preset(cfg, ORDER[0])
    print(f"start preset {ORDER[0]}, latency {hl.read_latency(lat)}", flush=True)

    durations: list[float] = []
    slow: list[tuple[float, str]] = []
    latencies: list = []
    index = 0
    started = time.monotonic()
    next_switch = started + args.cycle
    current = ORDER[0]

    while time.monotonic() - started < args.total:
        t0 = time.monotonic()
        out.writeframe(buf)
        ms = (time.monotonic() - t0) * 1000
        durations.append(ms)
        if ms > SLOW_MS:
            slow.append((ms, current))

        if time.monotonic() >= next_switch:
            next_switch += args.cycle
            index = (index + 1) % len(ORDER)
            current = ORDER[index]
            # No reset, no stop/start: exactly one register pair write.
            hl.write_preset(cfg, current)
            n = hl.read_latency(lat)
            latencies.append(n)
            print(f"[{time.strftime('%H:%M:%S')}] preset {current:<9} latency {n} "
                  f"(writes so far {len(durations)})", flush=True)
        time.sleep(0.2)

    print("\n--- summary ---", flush=True)
    print(f"frames written : {len(durations)}", flush=True)
    print(f"write time     : min {min(durations):.1f} ms, median "
          f"{statistics.median(durations):.1f} ms, max {max(durations):.1f} ms", flush=True)
    print(f"stalls > {SLOW_MS:.0f} ms: {len(slow)}", flush=True)
    for ms, name in slow[:5]:
        print(f"  {ms:.0f} ms while '{name}' was active", flush=True)
    unique = sorted({n for n in latencies if n is not None})
    print(f"latency values : {unique} (expected [21])", flush=True)

    ok = (len(slow) == 0 and len(durations) > 0 and unique == [21])
    print("RESULT: LIVE SWITCH STABLE" if ok else "RESULT: SOMETHING STALLED", flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
