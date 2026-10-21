#!/usr/bin/env python3
"""Does the HDMI output hardware work at all? Test the lowest pixel clock.

Why 640x480
    Every earlier output test ran at 720p (74.25 MHz) or 1080p (148.5 MHz) and none
    produced TMDS - not even with the unmodified PYNQ overlay. 640x480@60 has a
    25.175 MHz pixel clock, so it is the gentlest setting the board can be asked for.
    If the output works here the problem is the pixel rate (the PYNQ-Z2's HDMI ports
    are unbuffered, so drive strength and signal integrity matter); if it does not
    work even here, the output path or the connector is at fault.

How the test decides
    ``writeframe`` returns only after the VDMA has completed a frame transfer, and the
    VDMA can only complete one if v_axi4s_vid_out is consuming pixels - which needs a
    running video path and a running TMDS clock. So "did it return?" is a real pass/fail
    signal, independent of what any capture card shows.

    It must run in the main thread: writeframe uses asyncio.get_event_loop(), which
    raises in a secondary thread (that mistake produced a false "blocked" verdict once).

Run it under an external watchdog so a hang is visible as a missing line:

    timeout 20 sudo python3 -u hdmi_out_lowclk.py --mode 640x480
    # "RESULT: ... returned"  -> the output path consumed a frame
    # no RESULT line at all    -> it hung, i.e. nothing is being consumed
"""

from __future__ import annotations

import argparse
import time

STOCK = "/usr/local/share/pynq-venv/lib/python3.10/site-packages/pynq/overlays/base/base.bit"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bitstream", default=STOCK)
    ap.add_argument("--mode", default="640x480")
    ap.add_argument("--hold", type=float, default=30.0)
    args = ap.parse_args(argv)

    from pynq import Overlay
    from pynq.lib.video import VideoMode

    width, height = (int(v) for v in args.mode.lower().split("x"))
    print(f"loading {args.bitstream}", flush=True)
    base = Overlay(args.bitstream)
    video = base.video
    out = video.hdmi_out

    out.configure(VideoMode(width, height, 24, 60))
    out.start()
    print(f"hdmi_out configured and started at {width}x{height}", flush=True)
    print(f"  pixel clock 25.175 MHz, serial 125.9 MHz for 640x480", flush=True)

    frame = out.newframe()
    frame[:] = (0, 200, 0)
    print("frame filled with solid green; calling writeframe (main thread)", flush=True)

    started = time.monotonic()
    out.writeframe(frame)
    elapsed = time.monotonic() - started

    print(f"RESULT: writeframe returned after {elapsed:.2f}s", flush=True)
    print("  the VDMA consumed a frame, so the output path is running;", flush=True)
    print("  the capture card should show solid green", flush=True)
    try:
        time.sleep(args.hold)
    except KeyboardInterrupt:
        pass
    print("done", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
