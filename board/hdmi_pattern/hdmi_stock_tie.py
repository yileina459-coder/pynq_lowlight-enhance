#!/usr/bin/env python3
"""Control experiment: the *official* PYNQ passthrough on the stock overlay.

Reference: https://pynq.readthedocs.io/en/latest/pynq_libraries/video.html

    hdmi_in.configure()
    hdmi_out.configure(hdmi_in.mode)
    hdmi_in.start()
    hdmi_out.start()
    hdmi_in.tie(hdmi_out)          # stream input directly to output

Why this is the right control
    It uses the unmodified bitstream, the documented API order and the documented way
    of connecting input to output, so the only variables left are the cable, the
    capture card and the board's HDMI output hardware. If the monitor/capture card
    shows the laptop desktop here, then the board can drive 1080p and the problem is
    in our kernel insertion. If it does not, the board cannot drive 1080p and the
    output PLL range is the suspect.

The tie goes through the VDMA (frames land in DDR), so latency is high - this is a
correctness check, not the low-latency path.

    sudo python3 -u hdmi_stock_tie.py
"""

from __future__ import annotations

import argparse
import time

STOCK = "/usr/local/share/pynq-venv/lib/python3.10/site-packages/pynq/overlays/base/base.bit"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--wait", type=int, default=120)
    args = ap.parse_args(argv)

    from pynq import Overlay

    print("loading the stock base overlay", flush=True)
    base = Overlay(STOCK)
    video = base.video
    hdmi_in = video.hdmi_in
    hdmi_out = video.hdmi_out

    # configure() blocks until the capture library has detected input timing.
    print(f"configuring the input (up to {args.wait}s)...", flush=True)
    deadline = time.time() + args.wait
    while True:
        try:
            hdmi_in.configure()
            break
        except Exception as exc:                          # noqa: BLE001
            print(f"  not yet: {exc}", flush=True)
            if time.time() > deadline:
                print("RESULT: no input signal")
                return 2
            time.sleep(3)

    mode = hdmi_in.mode
    print(f"input: {mode.width}x{mode.height} @{getattr(mode, 'fps', '?')}", flush=True)

    hdmi_out.configure(mode)
    hdmi_in.start()
    hdmi_out.start()
    print("both frontends started; tying input to output", flush=True)
    hdmi_in.tie(hdmi_out)

    print("RESULT: TIED - the capture card should now show the source picture",
          flush=True)
    print("holding for 300 s (Ctrl-C to stop)", flush=True)
    try:
        for i in range(300):
            time.sleep(1)
            if i % 30 == 0:
                print(f"  ...{i}s still tied", flush=True)
    except KeyboardInterrupt:
        pass
    hdmi_in.tie(None)
    print("untied", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
