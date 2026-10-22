#!/usr/bin/env python3
"""Push a real image through the kernel and out of the HDMI port.

Why the source is the VDMA, not HDMI IN
    Measured on this board: the HDMI output only works at 640x480 (25.2 MHz pixel
    clock); 800x600, 720p and 1080p never consume a frame and never emit TMDS.
    The HDMI input cannot run at 640x480 either, because dvi2rgb's kClkRange tops out
    at 3 and 25.175 MHz needs 5 (VCO 629 MHz). So the frame source is the VDMA inside
    the video hierarchy, and the kernel sits between MM2S and the video output - the
    enhancement is still done in the pixel path, by hardware, on real pixels.

What it demonstrates
    * the kernel processes a 640x480 frame produced by the PS, in the PL, at line rate
    * switching presets changes what comes out of the HDMI connector
    * the bracketing stamps report the pipeline latency
    * ``writeframe`` returning is what proves the output really consumed the frame

    sudo python3 -u hdmi_vdma_demo.py --cycle 6
"""

from __future__ import annotations

import argparse
import time

import numpy as np

import hdmi_live as hl


def test_image(width: int, height: int) -> np.ndarray:
    """A frame that makes every enhancement visible.

    Deliberately contains: a smooth gradient (contrast/brightness changes show up as a
    shift of the ramp), dark text-like blocks on a mid-grey field (gain/knee changes
    show up as legibility), fine vertical lines (clarity/sharpening shows up as edge
    contrast), and a colour patch (mono/invert presets show up immediately).

    PYNQ's default colour space is BGR, so channels are written in that order.
    """
    img = np.zeros((height, width, 3), dtype=np.uint8)

    # Vertical gradient background.
    ramp = np.linspace(20, 235, height, dtype=np.uint8).reshape(height, 1)
    img[:, :, 0] = ramp
    img[:, :, 1] = ramp
    img[:, :, 2] = ramp

    # Dark blocks that look like lines of text, on a mid-grey band.
    band_top, band_height = height // 2 - 60, 120
    img[band_top:band_top + band_height, :, :] = 128
    for row in range(band_top + 10, band_top + band_height - 10, 22):
        left = 40
        while left < width - 60:
            run = int(30 + (left * 7) % 90)
            img[row:row + 10, left:min(left + run, width - 40), :] = 25
            left += run + 18

    # Fine vertical lines for sharpening.
    for x in range(0, width, 16):
        img[470:475, x:x + 8, :] = 240

    # Colour patch.
    img[10:70, 10:130, 2] = 220          # red-ish
    img[10:70, 140:260, 1] = 220         # green-ish
    img[10:70, 270:390, 0] = 220         # blue-ish
    return img


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bitstream", default="enhance_hdmi.bit")
    ap.add_argument("--mode", default="640x480")
    ap.add_argument("--preset", default="document", choices=sorted(hl.PRESETS))
    ap.add_argument("--cycle", type=float, default=6.0)
    args = ap.parse_args(argv)

    from pynq import Overlay
    from pynq.lib.video import VideoMode

    width, height = (int(v) for v in args.mode.lower().split("x"))

    print(f"loading {args.bitstream}", flush=True)
    ol = Overlay(args.bitstream)
    video = ol.video
    out = video.hdmi_out

    # Both HPD GPIOs come up tri-stated (dir = 0xFFFFFFFF), so writing the data register alone
    # does not drive the pin. A sink that never sees HPD asserted keeps its receiver disabled -
    # a capture dongle then shows its own test pattern while the board happily streams.
    hl.raise_input_hpd(ol)
    hl.raise_output_hpd(ol)
    print("hdmi_in + hdmi_out HPD asserted", flush=True)

    cfg = hl.find(ol, "gpio_enh_cfg")
    lat = hl.find(ol, "gpio_enh_lat")

    out.configure(VideoMode(width, height, 24, 60))
    out.start()
    print(f"hdmi_out running at {width}x{height}", flush=True)

    image = test_image(width, height)
    print(f"test image {image.shape}, mean {image.mean():.1f}", flush=True)

    order = [args.preset] if args.cycle <= 0 else [
        "pass", "clarity", "document", "night", "invert", "binarize", "split"]

    cycle = 0
    while True:
        for name in order:
            hl.write_preset(cfg, name)
            time.sleep(0.2)

            t0 = time.monotonic()
            frame = out.newframe()
            frame[:] = image
            out.writeframe(frame)
            elapsed = time.monotonic() - t0

            n = hl.read_latency(lat)
            txt = "not measured" if n is None else f"{n} pixel clocks"
            print(f"[{time.strftime('%H:%M:%S')}] preset {name:<9} "
                  f"writeframe {elapsed * 1000:6.1f} ms  latency {txt}", flush=True)
            if args.cycle <= 0:
                print("holding; Ctrl-C to stop", flush=True)
                while True:
                    time.sleep(1.0)
            else:
                time.sleep(args.cycle)
        cycle += 1


if __name__ == "__main__":
    raise SystemExit(main())
