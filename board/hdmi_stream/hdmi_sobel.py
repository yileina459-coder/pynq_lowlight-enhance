#!/usr/bin/env python3
"""HDMI streaming Sobel on PYNQ-Z2 (board side).

Loads the rebuilt base overlay that has the Sobel kernel inserted between the
HDMI input pixel packer and the HDMI output pixel unpacker, then configures the
input and output pipelines to the detected mode.

What this verifies
    * the custom overlay loads on this PYNQ image (the version-compatibility
      question that gated the whole HDMI route)
    * the HDMI input locks onto the source and reports a mode
    * the output pipeline starts without errors
    The processed picture itself can only be checked with a display or a capture
    card attached to HDMI OUT - the stream bypasses the frame buffer, so there is
    nothing for the PS to read back.

Why no tie()
    In the stock base overlay ``hdmi_in.tie(hdmi_out)`` routes frames through the
    VDMA frame buffer. This overlay already wires the stream directly through the
    kernel, so tying would just re-enable an unused DMA channel.

Usage
    python3 hdmi_sobel.py                 # run until Ctrl+C
    python3 hdmi_sobel.py --seconds 10    # run for 10 s and report
"""

from __future__ import annotations

import argparse
import sys
import time


def describe_mode(mode) -> str:
    if mode is None:
        return "None"
    try:
        return (f"{mode.width}x{mode.height} @ {mode.fps:.2f} Hz, "
                f"pixel clock {mode.pixel_clock:.2f} MHz")
    except AttributeError:
        return str(mode)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bitstream", default="sobel_hdmi.bit")
    ap.add_argument("--seconds", type=float, default=0,
                    help="run for N seconds then stop (0 = until Ctrl+C)")
    args = ap.parse_args(argv)

    from pynq import Overlay

    print(f"loading {args.bitstream}")
    ol = Overlay(args.bitstream)
    print(f"IPs in design: {len(ol.ip_dict)}")

    if not hasattr(ol, "video"):
        print("FAIL: no 'video' hierarchy - PYNQ did not bind the HDMI wrapper.")
        print("      Check that the bitstream and .hwh are the pair built by "
              "build/overlay_hdmi/build.bat.")
        return 1

    video = ol.video
    hdmi_in = video.hdmi_in
    hdmi_out = video.hdmi_out

    print("configuring HDMI input")
    hdmi_in.configure()

    mode = hdmi_in.mode
    print(f"detected input mode: {describe_mode(mode)}")
    if mode is None:
        print("FAIL: no HDMI input signal detected.")
        print("      Connect the laptop/HDMI source to HDMI IN and run again.")
        return 2

    print("configuring HDMI output to match")
    hdmi_out.configure(mode)

    hdmi_in.start()
    hdmi_out.start()
    print("pipeline running - HDMI OUT should now show the Sobel edge image")

    started = time.time()
    try:
        while True:
            time.sleep(0.5)
            if args.seconds and (time.time() - started) >= args.seconds:
                break
    except KeyboardInterrupt:
        print("\ninterrupted")

    hdmi_out.stop()
    hdmi_in.stop()
    elapsed = time.time() - started
    print(f"stopped after {elapsed:.1f} s")
    print("RESULT: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
