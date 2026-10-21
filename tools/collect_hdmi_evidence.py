"""File the HDMI capture sequence as evidence and build a poster composite.

The capture run produced seventeen frames of the same test image in different states.
They are selected and named by what is visible in them (a vertical split, a hard
threshold, an over-sharpened frame, the plain original) rather than by guessing which
preset was active at each PC timestamp, because the board clock and the PC clock are
not synchronised.

The three flickering frames the user noticed are the one-frame glitch the kernel reset
causes when the preset changes - the documented cost of the reset gate.
"""

from __future__ import annotations

import os
import shutil

from PIL import Image

ATTACH = r"C:\Users\79171\.dsh\attachments\v1\objects"
OUT = "board/hdmi_stream_enhance/evidence"

# hash -> (file name, what it shows)
SELECTION = {
    "c28b84200ab330deb559365fc3efe10ea898ceba5b5ec7fddd69565c1ab7da73":
        ("hdmi_capture_plain.png", "plain original: gradient, grey band, dark bars, colour patches"),
    "1b2ea6f096f6e09f2262d67129d285b32a4f3ae52d2124b30eb1956750d02b2d":
        ("hdmi_capture_split.png", "vertical split: left third untouched, right side processed"),
    "0b3d5f7c8c1e8ab4a80b80ff7355e13cd662138cea8cad5e79002d5ba28f0faf":
        ("hdmi_capture_binarize.png", "hard threshold: black field with a white band"),
    "4e00a28b16cbd4084b4f79d2e5698e3a7c07b7c88c82dd3e4efdb6b119aa748f":
        ("hdmi_capture_sharpened.png", "high contrast / over-sharpened state"),
    "54e8571eea761da0dfb2428ab26c22f6483748c7f96f14189d76f9634f37c78f":
        ("hdmi_capture_glitch.png", "the one-frame glitch during a preset change"),
}


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    saved = []
    for digest, (name, note) in SELECTION.items():
        src = os.path.join(ATTACH, digest[:2], digest)
        if not os.path.exists(src):
            print(f"missing {name}")
            continue
        dst = os.path.join(OUT, name)
        shutil.copyfile(src, dst)
        saved.append((dst, note))
        print(f"{name}: {note}")

    if len(saved) >= 4:
        # 2x2 composite for the poster: plain, split, binarize, sharpened.
        order = ["hdmi_capture_plain.png", "hdmi_capture_split.png",
                 "hdmi_capture_binarize.png", "hdmi_capture_sharpened.png"]
        tiles = []
        for name in order:
            path = os.path.join(OUT, name)
            if os.path.exists(path):
                tiles.append(Image.open(path).convert("RGB"))
        if len(tiles) == 4:
            w = min(t.width for t in tiles)
            h = min(t.height for t in tiles)
            tiles = [t.crop((0, 0, w, h)) for t in tiles]
            gap = 12
            canvas = Image.new("RGB", (w * 2 + gap, h * 2 + gap), (17, 17, 17))
            for index, tile in enumerate(tiles):
                x = (index % 2) * (w + gap)
                y = (index // 2) * (h + gap)
                canvas.paste(tile, (x, y))
            out = os.path.join(OUT, "hdmi_presets_2x2.png")
            canvas.save(out)
            print(f"composite: {out} ({canvas.width}x{canvas.height})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
