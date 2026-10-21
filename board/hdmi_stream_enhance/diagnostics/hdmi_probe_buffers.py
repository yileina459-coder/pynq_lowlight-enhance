#!/usr/bin/env python3
"""Read back the VDMA frame list and report what each buffer actually contains.

Why
    The flicker was observed as the picture alternating with a nearly black frame, and the
    obvious explanation is that PYNQ's VDMA cycles a three-entry frame list while only one
    entry ever got our image - the other two keeping the all-zero frame that start() queues.

    Whether that is true is not a matter of opinion: the buffers live in DDR and can be read
    back through the same numpy view the driver uses. If every entry holds the test image
    (mean around 124) the alternation cannot be caused by empty buffers, and the search
    moves elsewhere. If an entry is all zeros, the hypothesis is confirmed and the fix is to
    fill every entry before letting the display run.

    sudo python3 -u hdmi_probe_buffers.py
"""

from __future__ import annotations

import argparse

import numpy as np

import hdmi_live as hl


def test_image(width: int, height: int) -> np.ndarray:
    img = np.zeros((height, width, 3), dtype=np.uint8)
    ramp = np.linspace(20, 235, height, dtype=np.uint8).reshape(height, 1)
    img[:, :, 0] = ramp
    img[:, :, 1] = ramp
    img[:, :, 2] = ramp
    img[height // 2 - 60:height // 2 + 60, :, :] = 128
    img[10:70, 10:130, 2] = 220
    img[10:70, 140:260, 1] = 220
    img[10:70, 270:390, 0] = 220
    return img


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bitstream", default="enhance_hdmi.bit")
    ap.add_argument("--mode", default="640x480")
    ap.add_argument("--writes", type=int, default=4)
    args = ap.parse_args(argv)

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
    hl.write_preset(cfg, "pass")

    out.configure(VideoMode(width, height, 24, 60))
    out.start()

    channel = out._vdma.writechannel
    frames = channel._frames
    print(f"frame list length: {len(frames)}", flush=True)

    image = test_image(width, height)
    for _ in range(args.writes):
        frame = out.newframe()
        frame[:] = image
        out.writeframe(frame)
    print(f"image written {args.writes} times\n", flush=True)

    for index in range(len(frames)):
        try:
            entry = frames[index]
        except Exception as exc:                          # noqa: BLE001
            print(f"buffer {index}: cannot read ({exc})", flush=True)
            continue
        if entry is None:
            print(f"buffer {index}: empty slot (None)", flush=True)
            continue
        array = np.asarray(entry)
        print(f"buffer {index}: shape={array.shape} mean={array.mean():.1f} "
              f"min={array.min()} max={array.max()} "
              f"{'<-- ALL ZERO (black frame)' if array.max() == 0 else ''}",
              flush=True)

    print("\ninterpretation: every entry should look like the test image (mean near 124);",
          flush=True)
    print("an entry with max 0 is a black frame the display can cycle onto.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
