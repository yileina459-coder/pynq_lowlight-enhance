#!/usr/bin/env python3
"""Keep the two preset tables identical.

Why
    The board applies a preset from board/hdmi_stream_enhance/hdmi_live.py; the offline preview and
    the automatic choice use the table in tools/preview_enhance.py. If they drift, the preview
    promises something the hardware will not do - which is worse than having no preview, because it
    is believed.

    python tools/check_presets.py
"""

from __future__ import annotations

import sys


def table(path: str) -> dict:
    """Read the PRESETS assignment without importing the module.

    hdmi_live.py pulls in pynq inside its functions and is only importable on the board, so the
    assignment is extracted textually and evaluated. ast.literal_eval cannot be used because the
    table is built with dict(...) calls.
    """
    text = open(path, encoding="utf-8").read()
    start = text.find("PRESETS = {")
    if start < 0:
        raise SystemExit(f"PRESETS not found in {path}")

    depth = 0
    for index in range(text.find("{", start), len(text)):
        char = text[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                literal = text[start:index + 1]
                break
    else:
        raise SystemExit(f"unbalanced PRESETS braces in {path}")

    namespace: dict = {}
    exec(literal, {}, namespace)          # noqa: S102 - our own source file, no user input
    return namespace["PRESETS"]


def main() -> int:
    board = table("board/hdmi_stream_enhance/hdmi_live.py")
    tools = table("tools/preview_enhance.py")

    problems = []
    only_board = set(board) - set(tools)
    only_tools = set(tools) - set(board)
    if only_board:
        problems.append(f"only in hdmi_live.py: {sorted(only_board)}")
    if only_tools:
        problems.append(f"only in preview_enhance.py: {sorted(only_tools)}")
    for name in sorted(set(board) & set(tools)):
        if board[name] != tools[name]:
            problems.append(f"{name}: board={board[name]} tools={tools[name]}")

    if problems:
        print("PRESET CHECK FAIL")
        for p in problems:
            print("  -", p)
        return 1

    print(f"PRESET CHECK PASS ({len(board)} presets identical in both files)")
    for name in sorted(board):
        cfg = board[name]
        gain = cfg.get("gain_lo", 16) / 16
        print(f"  {name:9s} gain_lo {gain:4.1f}x  knee {cfg.get('knee', 255):3d}  "
              f"clarity {cfg.get('clarity', 16):2d}"
              + ("  [mono]" if cfg.get("mono") else "")
              + ("  [binarize]" if cfg.get("binarize") else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
