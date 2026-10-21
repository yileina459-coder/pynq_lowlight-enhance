#!/usr/bin/env python3
"""Show your own picture on the board's HDMI output, through the enhance kernel.

What this adds
    Every earlier demo pushed a synthetic test pattern. This one displays an arbitrary
    picture: a 640x480x3 raw frame produced by tools/make_frame.py, or an image file the
    board can decode itself if Pillow happens to be installed there.

    The picture is written into all four VDMA frame buffers, so the display never cycles
    onto a stale black frame, and the script then only touches the configuration - which is
    the whole point of the memory-configured kernel: a preset change is one register write,
    nothing is reset, and the picture changes on the next pixel instead of blanking.

Preset cycling
    --cycle 8 walks the preset list every 8 seconds. With --reset-on-switch it uses the old
    sequence (write the configuration, assert the kernel reset, rebuild the output path),
    which is what a port-configured bitstream needs.

Usage
    python3 hdmi_show_image.py --raw frame.bin
    python3 hdmi_show_image.py --raw frame.bin --preset binarize --hold 600
    python3 hdmi_show_image.py --raw frame.bin --cycle 8
"""

from __future__ import annotations

import argparse
import os
import signal
import time

import numpy as np

import hdmi_live as hl

ORDER = ["pass", "clarity", "reading", "document", "night", "invert", "binarize", "split"]


class _Watchdog(Exception):
    """Raised by the SIGALRM handler when a blocking call overruns its budget."""


def _on_alarm(signum, frame):        # noqa: ARG001
    raise _Watchdog()


signal.signal(signal.SIGALRM, _on_alarm)


def load_frame(args, width: int, height: int) -> np.ndarray:
    expected = width * height * 3
    if args.raw:
        data = np.fromfile(args.raw, dtype=np.uint8)
        if data.size != expected:
            raise SystemExit(f"{args.raw}: {data.size} bytes, expected {expected} "
                             f"({width}x{height}x3) - rebuild it with tools/make_frame.py")
        return data.reshape(height, width, 3)

    from PIL import Image
    with Image.open(args.image) as img:
        return np.asarray(img.convert("RGB").resize((width, height)), dtype=np.uint8)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bitstream", default="enhance_hdmi.bit")
    ap.add_argument("--mode", default="640x480")
    ap.add_argument("--raw", help="raw 640x480x3 frame from tools/make_frame.py")
    ap.add_argument("--image", help="picture the board decodes itself (needs Pillow)")
    ap.add_argument("--preset", default="pass", choices=sorted(hl.PRESETS))
    ap.add_argument("--cycle", type=float, default=0.0,
                    help="switch preset every N seconds (0 = fixed preset)")
    ap.add_argument("--hold", type=float, default=0.0,
                    help="keep the picture up for N seconds (0 = until Ctrl-C)")
    ap.add_argument("--reset-on-switch", action="store_true",
                    help="old sequence: reset the kernel and rebuild the output path")
    args = ap.parse_args(argv)

    if not args.raw and not args.image:
        raise SystemExit("give --raw frame.bin (see tools/make_frame.py) or --image photo.jpg")

    from pynq import Overlay
    from pynq.lib.video import VideoMode

    width, height = (int(v) for v in args.mode.lower().split("x"))

    print(f"loading {args.bitstream}", flush=True)
    ol = Overlay(args.bitstream)
    video = ol.video
    out = video.hdmi_out

    hpd = hl.find(ol, "gpio_hdmiin")
    if hpd is not None:
        hpd.mmio.write(0x00, 0x1)

    cfg = hl.find(ol, "gpio_enh_cfg")
    lat = hl.find(ol, "gpio_enh_lat")
    if cfg is None:
        raise SystemExit("gpio_enh_cfg not found - wrong bitstream?")

    frame_image = load_frame(args, width, height)
    print(f"picture {width}x{height}, mean {frame_image.mean():.1f}", flush=True)

    def push_frames(count: int = 4) -> None:
        for _ in range(count):
            buf = out.newframe()
            buf[:] = frame_image
            out.writeframe(buf)

    def start_output() -> None:
        out.configure(VideoMode(width, height, 24, 60))
        out.start()
        push_frames()

    def start_output_with_retry(tries: int = 3, seconds: int = 4) -> None:
        """Bring the output path up, tolerating a sink that is slow to start pulling.

        writeframe() only returns once the VDMA has completed a frame, so if the capture
        card has not locked onto the timing yet it waits indefinitely. That happened twice
        while testing - the same script blocked once and then ran fine - so instead of
        hanging, a stuck write is abandoned, the path restarted, and the attempt repeated.
        """
        for attempt in range(1, tries + 1):
            try:
                signal.alarm(seconds)
                start_output()
                signal.alarm(0)
                if attempt > 1:
                    print(f"  output path came up on attempt {attempt}", flush=True)
                return
            except _Watchdog:
                signal.alarm(0)
                print(f"  no frame consumed within {seconds}s (attempt {attempt}/{tries}), "
                      f"restarting the output path", flush=True)
                try:
                    out.stop()
                except Exception:                          # noqa: BLE001
                    pass
                time.sleep(1.0)
        raise SystemExit("the sink never consumed a frame - is the capture card connected "
                         "and is OBS (or any viewer) running?")

    hl.write_preset(cfg, args.preset)
    start_output_with_retry()
    n = hl.read_latency(lat)
    print(f"preset {args.preset} up, pipeline latency {n}", flush=True)

    started = time.monotonic()
    next_switch = time.monotonic() + args.cycle if args.cycle > 0 else None
    index = ORDER.index(args.preset) if args.preset in ORDER else 0

    try:
        while True:
            now = time.monotonic()
            if args.hold > 0 and now - started >= args.hold:
                break
            if next_switch is not None and now >= next_switch:
                next_switch = now + args.cycle
                index = (index + 1) % len(ORDER)
                name = ORDER[index]
                # The reset pulse is what a port-configured bitstream needs to re-sample its
                # latched configuration; the memory-configured one must not be reset, because
                # that is exactly what interrupts the pixel stream.
                hl.PULSE_RESET = args.reset_on_switch
                hl.write_preset(cfg, name)
                hl.PULSE_RESET = False
                if args.reset_on_switch:
                    out.stop()
                    start_output()
                n = hl.read_latency(lat)
                print(f"[{time.strftime('%H:%M:%S')}] preset {name:<9} latency {n}",
                      flush=True)
            time.sleep(0.25)
    except KeyboardInterrupt:
        pass

    print("done", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
