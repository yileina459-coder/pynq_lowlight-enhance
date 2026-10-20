#!/usr/bin/env python3
"""Repository consistency check for the documentation.

Why this exists
    The project went through several rounds where a number changed (seven presets
    became eight, 4.7x became 196.7x, "waiting for the capture card" became "HDMI
    blocked, see hdmi_status.md"). Every round risked leaving a stale claim behind,
    and a judge reading two documents that disagree is worse than one document with
    a gap.

    This checks three cheap things that catch almost all of that:

      1. suspicious phrases that usually mean stale text
      2. markdown links whose target file does not exist
      3. a few numbers that must agree across documents, with the value that the
         code and the measurements actually produced

    python tools/check_consistency.py           # report
    python tools/check_consistency.py --strict  # non-zero exit on findings
"""

from __future__ import annotations

import argparse
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Files that are chronological records rather than current claims. The log quotes
# the numbers that were true at the time, so flagging it would be wrong.
HISTORICAL = {"report/ai_collaboration_log.md"}

# Phrases that usually indicate something was left unfinished or that a fact has
# moved on. Each entry is (pattern, why it is suspicious, allowed-if-line-contains).
SUSPICIOUS = [
    (r"待采集卡", "the capture card has arrived; hdmi_status.md is the current state", ()),
    (r"7 个预设", "there are eight presets since `document` was added", ()),
    (r"7 预设", "there are eight presets since `document` was added", ()),
    (r"4\.7×", "the whole-frame measurement is 196.7x; 4.7x is the per-row figure",
     ("逐行", "per-row")),
    (r"TODO|FIXME|XXX", "unfinished marker", ()),
    (r"待补", "placeholder that should be filled or removed", ()),
]

# Numbers that must appear the same way everywhere they are quoted.
# (regex that must NOT appear, explanation)
FORBIDDEN_NUMBERS = [
    (r"0/2764801", "typo in the channel count"),
    (r"3108\.4 ms → 15\.6", "PS is 3108.4 ms and PL whole-frame is 15.8 ms"),
]

# Values worth reporting so a human can eyeball drift; not errors by themselves.
LANDMARKS = {
    "preset count": r"8 个预设|eight presets",
    "bit-exact channels": r"2764800",
    "whole-frame means": r"15\.8 ms",
    "speed-up": r"196\.7",
    "dma latency": r"16 个像素时钟|16 pixel clocks",
    "hdmi latency": r"21 个像素时钟|21 pixel clocks",
    "hdmi WNS": r"\+0\.242",
    "pattern WNS": r"\+0\.277",
}


def markdown_files() -> list[str]:
    out = []
    for root, dirs, files in os.walk(REPO):
        dirs[:] = [d for d in dirs
                   if d not in {".git", ".tmp", ".work", "proj", "export", "iprepo",
                                "__pycache__", "node_modules"}]
        for name in files:
            if name.endswith(".md"):
                out.append(os.path.join(root, name))
    return sorted(out)


LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")


def check_links(path: str) -> list[str]:
    problems = []
    base = os.path.dirname(path)
    text = open(path, encoding="utf-8").read()
    for target in LINK.findall(text):
        target = target.split("#")[0].strip()
        if not target or target.startswith(("http://", "https://", "mailto:")):
            continue
        if "<" in target or ">" in target:
            target = target.strip("<>")
        candidates = [os.path.join(base, target), os.path.join(REPO, target)]
        if not any(os.path.exists(c) for c in candidates):
            problems.append(f"{os.path.relpath(path, REPO)}: link target missing -> {target}")
    return problems


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--strict", action="store_true", help="exit non-zero on findings")
    args = ap.parse_args(argv)

    files = markdown_files()
    print(f"scanning {len(files)} markdown files\n")

    findings: list[str] = []
    for path in files:
        rel = os.path.relpath(path, REPO)
        text = open(path, encoding="utf-8").read()
        if rel.replace("\\", "/") in HISTORICAL:
            continue
        for pattern, why, allowed_with in SUSPICIOUS:
            for m in re.finditer(pattern, text):
                line_no = text[:m.start()].count("\n") + 1
                line_text = text.splitlines()[line_no - 1]
                if any(token in line_text for token in allowed_with):
                    continue
                findings.append(f"{rel}:{line_no}: '{m.group(0)}' - {why}")
        for pattern, why in FORBIDDEN_NUMBERS:
            if re.search(pattern, text):
                findings.append(f"{rel}: contains '{pattern}' - {why}")
        findings.extend(check_links(path))

    if findings:
        print("findings:")
        for f in findings:
            print(f"  {f}")
    else:
        print("no stale phrases, no broken links")

    print("\nlandmark values (report for drift, not errors):")
    for label, pattern in LANDMARKS.items():
        hits = [os.path.relpath(p, REPO) for p in files
                if re.search(pattern, open(p, encoding="utf-8").read())]
        where = f"{len(hits)} file(s): " + ", ".join(hits[:3]) if hits else "NOT MENTIONED"
        print(f"  {label:<20} {where}")

    print()
    if not findings:
        print("CONSISTENCY PASS")
        return 0
    print(f"CONSISTENCY: {len(findings)} finding(s)")
    return 1 if args.strict else 0


if __name__ == "__main__":
    raise SystemExit(main())
