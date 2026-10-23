"""File the final capture set and rebuild the poster composite.

The six frames are named by what is visible in them, not by guessing which preset was
active at each PC timestamp - the board clock and the PC clock are not synchronised, and
inventing a mapping would be worse than describing the evidence honestly.

What is visible:
    a  the plain original: smooth gradient, grey band with dark bars, colour patches
    b  noticeably brighter, with fine vertical striping across the gradient
    c  dark field, bars picked out, patches muted
    d  strongly desaturated / inverted-looking, heavy striping
    e  dark striped field with bright bars
    f  a vertical boundary about two thirds across: left side plain, right side processed
       - the split-screen preset, and the clearest single-frame proof that the kernel is
       acting on the live stream
"""

from __future__ import annotations

import os
import shutil

from PIL import Image

ATTACH = r"C:\Users\79171\.dsh\attachments\v1\objects"
OUT = "board/hdmi_stream_enhance/evidence"

FILES = {
    "e99b5e7094ed857009fe768155d0a715e198c4ff1897396393f89126b72e9e9f":
        "hdmi_final_a_plain.png",
    "6676f1489aee3c641c202b4160b452bd7b0c1f3066ea33fff7cd896958f639f3":
        "hdmi_final_b_brighter.png",
    "123e97e98238851fb948e9e86e94ca8ce7537838932371b3e47b98af2e2fce77":
        "hdmi_final_c_dark.png",
    "87e02bfec25f50bb94b74f778ef377d2b390cf41e72f6e1e40e3d767c418f4ad":
        "hdmi_final_d_desaturated.png",
    "10edf6113036ed0878da73ff465a954b7ddfb7c9444c30ad821315ad7251d9e9":
        "hdmi_final_e_inverted.png",
    "2a0a9491d37628162ebc69e17d3e77c25d3825ac9507082ec8f8107e099659a5":
        "hdmi_final_f_split.png",
}


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    saved = []
    for digest, name in FILES.items():
        src = os.path.join(ATTACH, digest[:2], digest)
        if not os.path.exists(src):
            print(f"missing {name}")
            continue
        dst = os.path.join(OUT, name)
        shutil.copyfile(src, dst)
        saved.append(dst)
        print(f"saved {name}")

    # Poster composite: plain, split, dark, brighter. The split goes second because it is
    # the single most persuasive frame.
    order = ["hdmi_final_a_plain.png", "hdmi_final_f_split.png",
             "hdmi_final_c_dark.png", "hdmi_final_b_brighter.png"]
    tiles = [Image.open(os.path.join(OUT, n)).convert("RGB")
             for n in order if os.path.exists(os.path.join(OUT, n))]
    if len(tiles) == 4:
        w = min(t.width for t in tiles)
        h = min(t.height for t in tiles)
        gap = 10
        canvas = Image.new("RGB", (w * 2 + gap, h * 2 + gap), (17, 17, 17))
        for index, tile in enumerate(tiles):
            x = (index % 2) * (w + gap)
            y = (index // 2) * (h + gap)
            canvas.paste(tile.crop((0, 0, w, h)), (x, y))
        out = os.path.join(OUT, "hdmi_presets_2x2.png")
        canvas.save(out)
        print(f"composite rebuilt: {out} ({canvas.width}x{canvas.height})")
    else:
        print(f"only {len(tiles)} tiles available; composite not rebuilt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
