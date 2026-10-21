"""Reorganise board/hdmi_stream_enhance and fix every reference to the moved files.

The folder accumulated 34 files during the HDMI bring-up: three demos, one shared library,
twenty-odd investigation scripts and seven notebooks, all flat. This script splits them by
role - demos and the library stay at the top, the investigation scripts go to diagnostics/,
the notebooks to notebooks/ - and then rewrites the paths in the documentation so nothing
dangles.

Moves use git mv where the file is tracked, so history follows the file.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path("board/hdmi_stream_enhance")

# Files that stay at the top level: bitstream, reports, the shared library and the demos.
KEEP = {
    "README.md", "enhance_hdmi.bit", "enhance_hdmi.hwh", "base.xsa",
    "timing_impl.rpt", "util_impl.rpt",
    "hdmi_live.py",            # library: preset table, pack(), write_preset()
    "hdmi_preset_only.py",     # main demo
    "hdmi_vdma_demo.py",       # alternative demo (writes a frame per preset)
    "hdmi_restore_hpd.py",     # utility: bring display 2 back after an overlay load
}

DIAGNOSTICS = [
    "hdmi_ab.py", "hdmi_after_fix.py", "hdmi_clk_probe.py", "hdmi_content_flip.py",
    "hdmi_enhance.py", "hdmi_first_preset.py", "hdmi_follow.py", "hdmi_hpd_out_test.py",
    "hdmi_hpd_probe.py", "hdmi_in_check.py", "hdmi_live_only.py", "hdmi_one_preset.py",
    "hdmi_passthrough.py", "hdmi_preset_stream.py", "hdmi_presets.py",
    "hdmi_probe_buffers.py", "hdmi_smooth_demo.py", "hdmi_solid.py",
    "hdmi_static_frame.py", "hdmi_stock_check.py", "hdmi_two_phase.py",
]

NOTEBOOKS = [
    "hdmi_check.ipynb", "hdmi_demo.ipynb", "hdmi_hpd_retry.ipynb", "hdmi_loopback.ipynb",
    "hdmi_loopback_ours.ipynb", "hdmi_stock_check.ipynb", "make_hdmi_notebooks.py",
    "make_hpd_notebook.py",
]


def git_mv(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if not src.exists():
        print(f"  skip missing {src.name}")
        return
    result = subprocess.run(["git", "mv", str(src), str(dst)],
                            capture_output=True, text=True)
    if result.returncode != 0:
        src.rename(dst)
        print(f"  moved (plain) {src.name}")
    else:
        print(f"  moved {src.name}")


def main() -> int:
    moves: list[tuple[Path, Path]] = []

    for name in DIAGNOSTICS:
        moves.append((ROOT / name, ROOT / "diagnostics" / name))
    for name in NOTEBOOKS:
        moves.append((ROOT / name, ROOT / "notebooks" / name))

    for src, dst in moves:
        git_mv(src, dst)

    # Any remaining file that is neither kept, moved, nor a directory becomes a leftover.
    leftovers = []
    for entry in ROOT.iterdir():
        if entry.is_dir() or entry.name in KEEP:
            continue
        leftovers.append(entry.name)
    if leftovers:
        print(f"\nleftover files still at the top level: {leftovers}")

    # Rewrite references across the documentation.
    mapping: dict[str, str] = {}
    for name in DIAGNOSTICS:
        mapping[f"board/hdmi_stream_enhance/{name}"] = f"board/hdmi_stream_enhance/diagnostics/{name}"
        mapping[f"board\\hdmi_stream_enhance\\{name}"] = f"board\\hdmi_stream_enhance\\diagnostics\\{name}"
    for name in NOTEBOOKS:
        mapping[f"board/hdmi_stream_enhance/{name}"] = f"board/hdmi_stream_enhance/notebooks/{name}"
        mapping[f"board\\hdmi_stream_enhance\\{name}"] = f"board\\hdmi_stream_enhance\\notebooks\\{name}"

    changed = 0
    for path in Path(".").rglob("*.md"):
        if ".tmp" in path.parts or ".work" in path.parts:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        original = text
        for old, new in mapping.items():
            text = text.replace(old, new)
        if text != original:
            path.write_text(text, encoding="utf-8")
            changed += 1
            print(f"  updated references in {path}")
    print(f"\n{changed} markdown files updated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
