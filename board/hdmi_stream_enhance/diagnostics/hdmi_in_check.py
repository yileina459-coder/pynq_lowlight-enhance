#!/usr/bin/env python3
"""Correctly detect whether the HDMI input is locked.

The bug this replaces
    Every earlier test polled ``video.hdmi_in.mode`` and treated ``None`` as "no
    input lock". Reading the PYNQ driver explains why ``None`` was guaranteed:

        # pynq/lib/video/hierarchies.py, class VideoIn
        @property
        def mode(self):
            return self._vdma.readchannel.mode        # the VDMA's *configured* mode

    and that field is only ever assigned inside ``VideoIn.configure()``::

        def configure(self, pixelformat=PIXEL_BGR):
            self._hdmi.start()                 # blocks until the input mode is known
            input_mode = self._hdmi.mode       # the real detected mode
            self._vdma.readchannel.mode = VideoMode(input_mode.width, ...)

    We never called ``configure()``, so ``readchannel.mode`` stayed ``None`` no matter
    what the FPGA was doing. The tests could not have reported a lock even if the
    input had been locked the whole time.

How to read it properly
    * ``video.hdmi_in._hdmi.mode``  - what the frontend actually detected (may raise)
    * ``video.hdmi_in.mode``        - the VDMA mode, valid only after ``configure()``

    sudo python3 -u hdmi_in_check.py [--wait 60]
"""

from __future__ import annotations

import argparse

import hdmi_live as hl


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bitstream", default="enhance_hdmi.bit")
    ap.add_argument("--wait", type=float, default=60.0,
                    help="seconds to wait for the input to stabilise")
    args = ap.parse_args(argv)

    from pynq import Overlay
    from pynq.lib.video import VideoMode

    print(f"loading {args.bitstream}", flush=True)
    ol = Overlay(args.bitstream)
    video = ol.video

    video.hdmi_out.configure(VideoMode(1280, 720, 24, 60))
    video.hdmi_out.start()
    print("hdmi_out configured and started (720p)", flush=True)

    hpd = hl.find(ol, "gpio_hdmiin")
    if hpd is not None:
        current = hpd.mmio.read(0x00)
        if current & 0x1 == 0:
            hpd.mmio.write(0x00, 0x1)
            print("HPD asserted", flush=True)
        else:
            print("HPD already asserted", flush=True)

    frontend = video.hdmi_in._hdmi
    print(f"waiting up to {args.wait:.0f}s for the input frontend...", flush=True)

    detected = None
    try:
        # Avoid VideoIn.configure(): it also configures the input VDMA, which this
        # low-latency overlay bypasses. The frontend itself reports the detected mode.
        frontend.start(init_timeout=max(1, int(args.wait)))
        detected = frontend.mode
    except LookupError as exc:
        print(f"  no stable HDMI timing detected: {exc}", flush=True)
    except Exception as exc:                              # noqa: BLE001
        print(f"  frontend start failed: {type(exc).__name__}: {exc}", flush=True)

    print()
    if detected is not None:
        print(f"RESULT: INPUT DETECTED {detected.width}x{detected.height} "
              f"@{getattr(detected, 'fps', '?')} Hz")
    else:
        # configure() may have succeeded without us seeing a mode above.
        try:
            vdma_mode = video.hdmi_in.mode
        except Exception as exc:                          # noqa: BLE001
            vdma_mode = f"raised {type(exc).__name__}"
        print(f"RESULT: no mode detected; VDMA mode = {vdma_mode}")
        print("  if the frontend never armed, the input really has no valid timing")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
