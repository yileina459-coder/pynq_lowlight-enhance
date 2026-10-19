#!/usr/bin/env python3
"""Check that the PS-side register translation matches the golden presets.

The board test writes nine numbers into the kernel's AXI-Lite registers and then
compares against `golden.render(rgb, preset)`. If the translation in
`board/enhance_dma/enhance_dma.py` were wrong, the board would disagree with the
golden model for a boring reason and the failure would look like a hardware bug.

This runs that translation on the host, with no hardware:

    python sim/enhance/test_preset_regs.py
"""

from __future__ import annotations

import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, "board", "enhance_dma"))

import golden_enhance as golden  # noqa: E402
from enhance_dma import preset_to_regs  # noqa: E402


def main() -> int:
    rng = np.random.default_rng(7)
    # Small image, same border policy; size only affects runtime, not the mapping.
    rgb = rng.integers(0, 256, size=(40, 64, 3), dtype=np.uint8)

    failures = 0
    for preset in sorted(golden.PRESETS):
        regs = preset_to_regs(preset, rgb.shape[1])
        via_regs = golden.enhance(rgb, **regs)
        via_render = golden.render(rgb, preset)
        diff = np.abs(via_regs.astype(np.int32) - via_render.astype(np.int32))
        bad = int(np.count_nonzero(diff))
        print(f"  {preset:<9} mismatched {bad}/{diff.size}"
              f"   regs: clarity={regs['clarity']} knee={regs['knee']} "
              f"lo={regs['gain_lo']} hi={regs['gain_hi']} t={regs['thresh']} "
              f"bin={regs['binarize']} inv={regs['invert']} mono={regs['mono']} "
              f"split={regs['split_x']}")
        if bad:
            failures += 1

    # The identity preset is the strongest single check: any register that is
    # ignored or mis-translated tends to break identity first.
    identity = golden.enhance(rgb, **preset_to_regs("pass", rgb.shape[1]))
    if not np.array_equal(identity, rgb):
        print("FAIL: the 'pass' preset is not an exact identity")
        failures += 1

    print()
    if failures:
        print(f"PRESET REG TEST FAIL ({failures})")
        return 1
    print("PRESET REG TEST PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
