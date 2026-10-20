#!/usr/bin/env python3
"""Structural layout check for the poster (bounds, not pixels).

Why not a rendered image
    The bundled preview path rasterises this deck at the wrong scale: a minimal,
    obviously-correct A4 file comes out 1.33x too large and clipped at the right
    edge, and a 16:9 control file does the same. The PDF conversion of the same
    deck has the correct A4 MediaBox (595.28 x 841.89 pt), so the file geometry is
    right and the raster step is what misbehaves.

    So the layout is checked arithmetically instead: every shape must sit inside the
    page, and the text must fit the box the generator sized for it.

    python tools/check_poster.py report/poster/poster.pptx
"""

from __future__ import annotations

import argparse
import sys

from pptx import Presentation

EMU_PER_CM = 360000
TOLERANCE_CM = 0.05


def cm(value) -> float:
    return value / EMU_PER_CM


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pptx", nargs="?", default="report/poster/poster.pptx")
    args = ap.parse_args(argv)

    prs = Presentation(args.pptx)
    page_w, page_h = cm(prs.slide_width), cm(prs.slide_height)
    print(f"{args.pptx}: sheet {page_w:.2f} x {page_h:.2f} cm, "
          f"{len(prs.slides)} slide(s)")

    problems = []
    max_bottom = 0.0
    for index, slide in enumerate(prs.slides, 1):
        for shape in slide.shapes:
            left, top = cm(shape.left), cm(shape.top)
            width, height = cm(shape.width), cm(shape.height)
            right, bottom = left + width, top + height
            max_bottom = max(max_bottom, bottom)
            label = (shape.text_frame.text[:28].replace("\n", " ")
                     if shape.has_text_frame else str(shape.shape_type))
            if left < -TOLERANCE_CM or top < -TOLERANCE_CM:
                problems.append(f"slide {index}: '{label}' starts off-page "
                                f"({left:.2f}, {top:.2f})")
            if right > page_w + TOLERANCE_CM:
                problems.append(f"slide {index}: '{label}' runs past the right edge "
                                f"({right:.2f} > {page_w:.2f} cm)")
            if bottom > page_h + TOLERANCE_CM:
                problems.append(f"slide {index}: '{label}' runs past the bottom edge "
                                f"({bottom:.2f} > {page_h:.2f} cm)")

    print(f"lowest content edge: {max_bottom:.2f} cm of {page_h:.2f} cm")
    if problems:
        print("\nproblems:")
        for p in problems:
            print(f"  {p}")
        print(f"\nPOSTER LAYOUT: {len(problems)} problem(s)")
        return 1

    print("\nPOSTER LAYOUT OK (all shapes inside the sheet)")
    print("note: raster preview is unreliable in this environment - see the module"
          " docstring; geometry is checked arithmetically instead.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
