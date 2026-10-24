#!/usr/bin/env python3
"""Turn any picture into the 640x480 PNG the board displays, with a predictable fit.

Why a separate step
    The board can resize by itself, but doing it here means the operator sees exactly what the
    panel will show (including the letterbox bars) before it goes over the network, and the upload
    is a plain PNG that Pillow opens without surprises.

Fits
    letterbox  keep the aspect ratio, pad with the background colour (default: black)
    crop       keep the aspect ratio, fill the frame and cut the overflow (no bars)
    stretch    ignore the aspect ratio and fill the frame (faces get wider)

    python tools/prepare_image.py photo.jpg --out out/mine_640x480.png
    python tools/prepare_image.py photo.jpg --fit crop --background 32
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter, ImageOps

# The board's tone curve is two-segment: below the knee y*gain_lo/16, above it
# knee + (y-knee)*gain_hi/16. These are the same numbers as the board presets, so a picture
# brightened here looks like the one the kernel would produce - it just happens on the PC.
TONE_PRESETS = {
    "bright":   dict(clarity=24, knee=192, gain_lo=56, gain_hi=20),
    "night":    dict(clarity=28, knee=224, gain_lo=72, gain_hi=24),
    "document": dict(clarity=20, knee=192, gain_lo=64, gain_hi=16),
    "reading":  dict(clarity=24, knee=48,  gain_lo=88, gain_hi=14),
}


def flatten_illumination(rgb: np.ndarray, sigma: float = 28.0, target: float = 195.0,
                         strength: float = 1.0) -> np.ndarray:
    """Divide out the lighting, so the paper is the same brightness everywhere.

    The page photo has a strong top-right to bottom-left gradient (a lamp on one side). A global
    stretch cannot fix that: it has to either leave the gradient alone, or push the bright end to
    white and lose the paper there - which is the glare patch the fixed curves produced.

    Dividing the luma by a blurred copy of itself removes the low-frequency lighting while keeping
    the high-frequency ink, which is the classic way to flatten a document scan. A partial strength
    keeps a little of the original shading so the page does not look like flat cardboard.
    """
    r = rgb[..., 0].astype(np.float32)
    g = rgb[..., 1].astype(np.float32)
    b = rgb[..., 2].astype(np.float32)
    y = (77 * r + 150 * g + 29 * b) / 256.0

    blurred = Image.fromarray(np.clip(y, 0, 255).astype(np.uint8)).filter(
        ImageFilter.GaussianBlur(sigma))
    background = np.maximum(np.asarray(blurred, dtype=np.float32), 6.0)

    gain = target / background
    gain = 1.0 + (gain - 1.0) * float(strength)
    y2 = np.clip(y * gain, 0, 255)
    delta = (y2 - y)[..., None]
    return np.clip(rgb.astype(np.float32) + delta, 0, 255).astype(np.uint8)


def normalize_page(rgb: np.ndarray, low_pct: float = 10, high_pct: float = 85,
                   out_low: int = 18, out_high: int = 240) -> np.ndarray:
    """Stretch the ink and paper levels to a fixed range, per picture.

    A fixed tone curve cannot serve a photo of a page: the shadowed corner and the lit paper end up
    in very different places depending on the light, and a large low-end gain turns the shadow into a
    blown-out white blob (that is exactly what the 'reading' curve did to the test photo). Measuring
    where the ink and the paper actually sit and mapping those to 18..240 keeps the whole page in
    range without clipping, and keeps the lighting gradient as a gradient instead of a blob.
    """
    r = rgb[..., 0].astype(np.int32)
    g = rgb[..., 1].astype(np.int32)
    b = rgb[..., 2].astype(np.int32)
    y = (77 * r + 150 * g + 29 * b) >> 8

    ink = np.percentile(y, low_pct)
    paper = np.percentile(y, high_pct)
    if paper - ink < 8:                       # flat or almost flat picture: leave it alone
        return rgb
    scale = (out_high - out_low) / (paper - ink)
    y2 = np.clip((y - ink) * scale + out_low, 0, 255)
    delta = (y2 - y)[..., None]
    return np.clip(rgb.astype(np.int32) + delta, 0, 255).astype(np.uint8)


def apply_tone(rgb: np.ndarray, preset: dict) -> np.ndarray:
    """Apply the board's two-segment tone curve to the luma and carry the delta into RGB.

    Identical arithmetic to src/hls/enhance/enhance_body.inc stage 3 and 5 (minus the local
    contrast stage, which the board still runs), so this is a preview of the same curve rather
    than a different one.
    """
    r = rgb[..., 0].astype(np.int32)
    g = rgb[..., 1].astype(np.int32)
    b = rgb[..., 2].astype(np.int32)
    y = (77 * r + 150 * g + 29 * b) >> 8

    knee = preset.get("knee", 255)
    gain_lo = preset.get("gain_lo", 16)
    gain_hi = preset.get("gain_hi", 16)
    below = (y * gain_lo) >> 4
    above = knee + (((y - knee) * gain_hi) >> 4)
    y2 = np.where(y <= knee, below, above)
    y2 = np.clip(y2, 0, 255)

    delta = (y2 - y)[..., None]
    return np.clip(rgb.astype(np.int32) + delta, 0, 255).astype(np.uint8)

WIDTH, HEIGHT = 640, 480


def swap_red_blue(img):
    """Exchange the red and blue channels.

    The board displays red as blue and blue as red - verified on hardware with a pure red frame, which came
    back as (0, 0, 245), and with a colour-band test in which red/blue and yellow/cyan traded places while
    green and magenta did not move. Swapping here makes every upload appear in its true colours.

    If a future bitstream corrects the output packing order, delete this and its two call sites.
    """
    from PIL import Image as _Image
    import numpy as _np
    array = _np.asarray(img)
    if array.ndim == 3 and array.shape[2] >= 3:
        # Image.fromarray must come from the PIL module, not img.__class__: an opened file is a
        # PngImageFile, which has no fromarray, and that is exactly how the first version of this failed.
        return _Image.fromarray(array[..., [2, 1, 0]])
    return img


def load(path: str) -> Image.Image:
    """Open any picture Pillow understands, honouring EXIF orientation (phone photos)."""
    img = Image.open(path)
    img = ImageOps.exif_transpose(img)
    return img.convert("RGB")


def fit(img: Image.Image, mode: str, background: int) -> Image.Image:
    if mode == "stretch":
        return img.resize((WIDTH, HEIGHT), Image.LANCZOS)

    src_w, src_h = img.size
    scale = (WIDTH / src_w) if mode == "crop" else min(WIDTH / src_w, HEIGHT / src_h)
    scale = max(scale, HEIGHT / src_h) if mode == "crop" else scale
    new_w, new_h = max(1, round(src_w * scale)), max(1, round(src_h * scale))
    resized = img.resize((new_w, new_h), Image.LANCZOS)

    canvas = Image.new("RGB", (WIDTH, HEIGHT), (background, background, background))
    if mode == "crop":
        left = (new_w - WIDTH) // 2
        top = (new_h - HEIGHT) // 2
        canvas.paste(resized, (-left, -top))
    else:
        canvas.paste(resized, ((WIDTH - new_w) // 2, (HEIGHT - new_h) // 2))
    return canvas


def _legibility(rgb: np.ndarray) -> float:
    """Same shape of metric as tools/score_capture.py, applied to the frame before upload.

    Scoring offline means the choice costs nothing: no upload, no board, no screenshot.
    """
    r = rgb[..., 0].astype(np.int32)
    g = rgb[..., 1].astype(np.int32)
    b = rgb[..., 2].astype(np.int32)
    y = (77 * r + 150 * g + 29 * b) >> 8
    contrast = float(np.percentile(y, 95) - np.percentile(y, 5))
    clip = float(((y <= 2) | (y >= 253)).mean() * 100)
    midtone = float(((y >= 60) & (y <= 200)).mean() * 100)
    lap = (4 * y[1:-1, 1:-1] - y[:-2, 1:-1] - y[2:, 1:-1] - y[1:-1, :-2] - y[1:-1, 2:])
    edge = float(np.abs(lap).mean())
    return (contrast * 0.6 + edge * 8.0 + midtone * 0.8
            - max(0.0, clip - 5) * 3.0 - abs(float(y.mean()) - 130) * 0.25)


def looks_like_document(rgb: np.ndarray) -> bool:
    """True when the picture is mostly paper with ink on it.

    A page under uneven light has one dominant bright mode (the paper) covering a large share of the
    frame, with the ink well below it. Photos rarely look like that. The distinction matters because
    the two families want different curves: a page wants the adaptive stretch that pins the paper to
    a fixed level (no glare), while a photo wants a tone curve that keeps its shadows.
    """
    y = ((77 * rgb[..., 0].astype(np.int32)
          + 150 * rgb[..., 1].astype(np.int32)
          + 29 * rgb[..., 2].astype(np.int32)) >> 8)
    hist, edges = np.histogram(y, bins=32, range=(0, 256))
    centres = (edges[:-1] + edges[1:]) / 2
    bright_modes = centres > 90
    if not bright_modes.any():
        return False
    top = int(np.argmax(np.where(bright_modes, hist, 0)))
    peak = centres[top]
    paper_share = float(((y > peak - 16) & (y < peak + 16)).mean())
    ink_share = float((y < peak - 40).mean())
    return paper_share > 0.22 and ink_share > 0.03


def choose_tone(rgb: np.ndarray) -> tuple[str, list[tuple[str, float]]]:
    """Pick the curve that makes this particular picture most readable.

    Candidates are the fixed curves plus the adaptive page normalisation, plus doing nothing.
    The adaptive one usually wins on photographs of text and the fixed ones on ordinary dark
    photos, but which is which depends on the light in the picture - so it is measured instead of
    assumed.
    """
    scores: list[tuple[str, float]] = [("none", _legibility(rgb))]
    for name, preset in TONE_PRESETS.items():
        scores.append((name, _legibility(apply_tone(rgb, preset))))
    scores.append(("page", _legibility(normalize_page(flatten_illumination(rgb)))))
    if looks_like_document(rgb):
        # Documents go to the adaptive stretch regardless of the raw score: it is the only candidate
        # that pins the paper level, so the page cannot develop a glare patch where the light fell
        # unevenly. The fixed curves score well on contrast while blowing exactly that patch.
        return "page", scores
    best = max(scores, key=lambda item: item[1])
    return best[0], scores


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("image", help="source picture (any format Pillow reads)")
    ap.add_argument("--out", required=True, help="output PNG path")
    ap.add_argument("--fit", choices=("letterbox", "crop", "stretch"), default="letterbox")
    ap.add_argument("--background", type=int, default=0, help="letterbox colour 0..255")
    ap.add_argument("--tone", choices=sorted(TONE_PRESETS) + ["page", "auto"], default=None,
                    help="apply a brightness curve here instead of on the board")
    args = ap.parse_args(argv)

    source = Path(args.image)
    if not source.is_file():
        print(f"PREPARE FAIL: no such file: {source}")
        return 1

    img = load(str(source))
    fitted = fit(img, args.fit, args.background)
    if args.tone:
        before = np.asarray(fitted).mean()
        if args.tone == "auto":
            chosen, scores = choose_tone(np.asarray(fitted))
            print("tone candidates: " + ", ".join(f"{n}={s:.0f}" for n, s in
                                                   sorted(scores, key=lambda i: -i[1])))
            print(f"tone auto -> {chosen}")
            args.tone = chosen
            if chosen == "none":
                fitted.save(args.out) if False else None
        if args.tone == "none":
            pass
        elif args.tone == "page":
            # Flatten the lighting first. A global stretch alone cannot fix a page lit from one
            # side: it can only trade a pale corner against dim text at the other end, which is
            # exactly what the pure-stretch version did. Dividing by a blurred copy of the luma
            # removes the gradient and leaves the ink, then the stretch pins the paper level.
            prepared = np.asarray(fitted)
            fitted = Image.fromarray(normalize_page(flatten_illumination(prepared)))
        else:
            fitted = Image.fromarray(apply_tone(np.asarray(fitted), TONE_PRESETS[args.tone]))
        print(f"tone {args.tone}: brightness {before:.0f} -> {np.asarray(fitted).mean():.0f}")
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    fitted = swap_red_blue(fitted) if args.fit else fitted
    fitted.save(out, "PNG")

    pixels = np.asarray(fitted)
    print(f"source {img.size[0]}x{img.size[1]} -> {WIDTH}x{HEIGHT} ({args.fit})")
    print(f"wrote {out}  mean={pixels.mean():.1f}  min={pixels.min()}  max={pixels.max()}")
    if pixels.max() < 8:
        print("WARNING: the result is almost black - is the source picture dark?")
    return 0


if __name__ == "__main__":
    sys.exit(main())
