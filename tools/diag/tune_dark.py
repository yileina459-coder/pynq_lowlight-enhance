"""Autonomous tuning loop: try combinations on the board, capture, score, keep the best.

Why this exists
    Tuning a low-light pipeline by eye across a dozen parameter sets is slow and unreliable - and the two
    stages involved are hard to reason about together: the PC applies a tone curve, the board adds
    local contrast with a gain of its own. This script drives the whole chain by itself:

      for each (tone, clarity) candidate:
          build the frame locally, upload, set the board preset, wait, capture the screen,
          score the capture, keep the numbers

    It needs the OBS window to be visible (the capture comes from the desktop) and the video
    rectangle to be known - tools/score_capture.py's --crop. It prints a ranked table so the choice
    is evidence-based rather than "looks better".

    python tools/diag/tune_dark.py photo.jpg --crop 44,219,818,801 --out .tmp/tune
"""

from __future__ import annotations

import argparse
import itertools
import json
import subprocess
import os
import shutil
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

def _repo_root() -> Path:
    """The repository root: walk up until the directory that holds .git.

    tools/ used to be flat, so Path(__file__).parent.parent was the root. Scripts now live at different
    depths (tools/, tools/diag/, tools/archive/), and hard-coding the depth is exactly what broke when
    they moved - so the layout is discovered instead.
    """
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / ".git").exists():
            return parent
    return here.parents[2] if len(here.parents) > 2 else here.parent

PYTHON = os.environ.get("PYTHON") or shutil.which("python") or sys.executable
REPO = _repo_root()
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from prepare_image import TONE_PRESETS, apply_tone, fit, load  # noqa: E402
from score_capture import legibility, score  # noqa: E402

def screenshot(path: Path) -> None:
    ps = f"""
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$b = [System.Windows.Forms.SystemInformation]::VirtualScreen
$bmp = New-Object System.Drawing.Bitmap $b.Width, $b.Height
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($b.Left, $b.Top, 0, 0, $bmp.Size)
$bmp.Save("{path}", [System.Drawing.Imaging.ImageFormat]::Png)
$g.Dispose(); $bmp.Dispose()
"""
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True, capture_output=True)

def upload(local_png: Path, remote_name: str) -> bool:
    result = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
         str(REPO / "tools" / "board" / "show_image.ps1"),
         "-Image", str(local_png), "-Preset", "clarity", "-KeepLocal"],
        capture_output=True, text=True)
    return "OK - the board is now showing" in (result.stdout or "")

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("image")
    ap.add_argument("--crop", required=True, help="x0,y0,x1,y1 of the video area on screen")
    ap.add_argument("--out", required=True)
    ap.add_argument("--fits", default="crop")
    args = ap.parse_args(argv)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    crop = tuple(int(v) for v in args.crop.split(","))

    source = load(args.image)
    base = fit(source, "crop", 0)
    Image.fromarray(np.asarray(base)).save(out / "candidate_source.png")

    rows = []
    # Nothing done at all, as the reference point.
    candidates = [("none", None), ("none+clarity", None)]
    for tone in TONE_PRESETS:
        candidates.append((tone, tone))

    for label, tone in candidates:
        fitted = np.asarray(base)
        if tone:
            fitted = apply_tone(fitted, TONE_PRESETS[tone])
        local = out / f"cand_{label}.png"
        Image.fromarray(fitted).save(local)

        if not upload(local, local.name):
            print(f"{label}: upload failed, skipping")
            continue
        time.sleep(3.5)
        shot = out / f"shot_{label}.png"
        screenshot(shot)
        s = score(str(shot), crop)
        rows.append({"label": label, "tone": tone or "", **s, "legibility": legibility(s)})
        print(f"{label:14s} mean {s['mean']:5.1f} contrast {s['contrast']:5.1f} "
              f"clip {s['clip']:4.1f}% edge {s['edge']:5.2f} -> {legibility(s):6.1f}")

    if not rows:
        print("TUNE FAIL: nothing measured")
        return 1

    rows.sort(key=lambda r: r["legibility"], reverse=True)
    print("\nranked:")
    for r in rows:
        print(f"  {r['legibility']:6.1f}  {r['label']}")
    (out / "ranking.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print(f"\nwrote {out / 'ranking.json'}")
    print(f"BEST: {rows[0]['label']}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
