"""Rank the PC-side tone presets on a dark picture, offline, with the metric the board uses.

Why offline
    A board round trip is about thirty seconds per candidate. Worse, an earlier attempt at tuning
    ranked the *worst* candidate first, because the metric it used rewarded blown highlights. The
    metric here is tools/score_capture.legibility, which pulls the mean toward 130 and penalises
    clipping, and the kernel is simulated with tools/preview_enhance.enhance so the numbers describe
    what the board will actually show.

    python tools/rank_tones.py data/images/test_dim_720p.png
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import preview_enhance  # noqa: E402
from prepare_image import (TONE_PRESETS, apply_tone, choose_tone, fit,  # noqa: E402
                           flatten_illumination, load, normalize_page)
from score_capture import legibility, score  # noqa: E402

# What the board runs for low-light observation: local contrast only, no hardware gain.
BOARD_PRESET = {"clarity": 28, "knee": 255, "gain_lo": 16, "gain_hi": 16}


def tone(named: str, frame: Image.Image) -> Image.Image:
    """Apply one named tone the same way tools/prepare_image.py does."""
    if named == "none":
        return frame
    if named == "page":
        return Image.fromarray(normalize_page(flatten_illumination(np.asarray(frame))))
    if named == "auto":
        chosen, _ = choose_tone(np.asarray(frame))
        return tone(chosen, frame)
    return Image.fromarray(apply_tone(np.asarray(frame), TONE_PRESETS[named]))


def simulate(img: Image.Image) -> Image.Image:
    arr = np.asarray(img.convert("RGB"))
    return Image.fromarray(preview_enhance.enhance(arr, BOARD_PRESET).astype("uint8"))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("image")
    ap.add_argument("--fit", default="letterbox", choices=("letterbox", "crop", "stretch"))
    args = ap.parse_args(argv)

    frame = fit(load(args.image), args.fit, 0)
    names = ["none", "page", "auto"] + list(TONE_PRESETS)

    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        for name in names:
            shown = simulate(tone(name, frame))
            path = Path(tmp) / f"{name}.png"
            shown.save(path)
            s = score(str(path), None)
            rows.append((name, legibility(s), s))

    rows.sort(key=lambda row: -row[1])
    print(f"{'tone':10s} {'legibility':>10s} {'mean':>6s} {'contrast':>8s} {'edge':>6s} {'clip%':>6s}")
    for name, value, s in rows:
        print(f"{name:10s} {value:10.1f} {s['mean']:6.1f} {s['contrast']:8.1f} "
              f"{s['edge']:6.2f} {s['clip']:6.1f}")
    print(f"\nBEST: {rows[0][0]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
