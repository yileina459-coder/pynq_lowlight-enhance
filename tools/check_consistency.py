#!/usr/bin/env python3
"""Repository consistency check for the documentation.

Why this exists
    The project went through several rounds where a number changed (eight presets
    became ten, the offset "0.3 px" became "per pixel stream, calibrate each start",
    4.7x became 196.7x, "waiting for the capture card" became "HDMI blocked, see
    hdmi_status.md"). Every round risked leaving a stale claim behind, and a judge
    reading two documents that disagree is worse than one document with a gap.

    This checks four cheap things that catch almost all of that:

      1. suspicious phrases that usually mean stale text
      2. markdown links whose target file does not exist
      3. a few numbers that must agree across documents, with the value that the
         code and the measurements actually produced
      4. script encodings (.ps1 BOM / .bat ASCII)

    The single source of truth for those numbers is docs/facts.md.

    python tools/check_consistency.py           # report
    python tools/check_consistency.py --strict  # non-zero exit on findings
"""

from __future__ import annotations

import argparse
import os
import pathlib
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Files that are chronological records rather than current claims. The log quotes
# the numbers that were true at the time, so flagging it would be wrong. Each of these
# files carries a banner saying which part is history and where the current baseline is.
HISTORICAL = {
    "report/ai_collaboration_log.md",
    "docs/hdmi_status.md",
    "docs/session_handoff.md",
    "docs/video_demo.md",
    "docs/p3b_plan.md",
    "docs/dma_investigation.md",
    "board/hdmi_stream_enhance/README.md",
    "board/dma_sobel/README.md",
    "board/hdmi_stream/README.md",
    "board/hdmi_pattern/README.md",
    "board/enhance_dma/README.md",
}

# Phrases that usually indicate something was left unfinished or that a fact has
# moved on. Each entry is (pattern, why it is suspicious, allowed-if-line-contains).
SUSPICIOUS = [
    (r"待采集卡", "the capture card has arrived; hdmi_status.md is the current state", ()),
    (r"7 个预设", "there are ten presets since `crisp` was added", ()),
    (r"7 预设", "there are ten presets since `crisp` was added", ()),
    (r"7 档", "the runtime table has ten presets; 7 was a 2026-10-21 snapshot",
     ("当时", "历史", "旧", "归档")),
    (r"4\.7×", "the whole-frame measurement is 196.7x; 4.7x is the per-row figure",
     ("逐行", "per-row")),
    (r"实时(增强|视频|出图|图像|工作)", "the camera-to-screen link is not open; say 持续出图 / 逐帧处理",
     ("不写", "「实时」", "\"实时\"")),
    (r"端到端延迟(只有|约)一行", "end-to-end latency was never measured", ("不写", "「", "历史")),
    (r"0\.3 (像素|px)", "the offset is per pixel stream; the 0.3 px reading was one stream",
     ("历史", "早期", "曾有", "一次", "不写", "统一", "旧")),
    (r"\+0\.(289|354|171)", "the delivered bitstream is +0.206 ns; these were intermediate builds",
     ("那一版", "中间版本", "历史", "当时", "旧", "本文中间")),
    (r"未开始|待做|待补|TODO|FIXME|XXX", "unfinished marker", ()),
]

# Numbers that must appear the same way everywhere they are quoted.
# (regex that must NOT appear, explanation)
FORBIDDEN_NUMBERS = [
    (r"0/2764801", "typo in the channel count"),
    (r"3108\.4 ms → 15\.6", "PS is 3108.4 ms and PL whole-frame is 15.8 ms"),
]

# Values worth reporting so a human can eyeball drift; not errors by themselves.
LANDMARKS = {
    "baseline (facts)": r"docs/facts\.md",
    "runtime presets": r"10 档|10 个预设|ten presets",
    "verified preset table": r"8 档|eight presets",
    "bit-exact channels": r"2764800",
    "enhance frame": r"15\.6 ms",
    "sobel whole frame": r"15\.8 ms",
    "speed-up": r"196\.7",
    "dma latency": r"16 个像素时钟|16 pixel clocks",
    "hdmi latency": r"21 拍|21 个像素时钟|21 pixel clocks",
    "delivered WNS": r"\+0\.206",
    "bitstream md5": r"c9a27af6",
    "offset calibration": r"216\.8|218",
}


def markdown_files() -> list[str]:
    out = []
    for root, dirs, files in os.walk(REPO):
        dirs[:] = [d for d in dirs
                   if d not in {".git", ".tmp", ".work", "proj", "export", "iprepo",
                                "build", "dist", "__pycache__", "node_modules"}]
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



def check_baseline() -> list[str]:
    """The facts page must exist and README must point at it."""
    findings = []
    facts = os.path.join(REPO, "docs", "facts.md")
    if not os.path.exists(facts):
        findings.append("docs/facts.md: missing - it is the single source of truth")
    readme = os.path.join(REPO, "README.md")
    if os.path.exists(readme) and "docs/facts.md" not in open(readme, encoding="utf-8").read():
        findings.append("README.md: does not link docs/facts.md")
    return findings


def check_script_encodings() -> list[str]:
    """Chinese in a script must be stored the way the interpreter actually reads it.

    This bit twice in one evening, both times silently at the *user*: a .ps1 without a UTF-8 BOM is read
    by PowerShell 5.1 in the OEM code page, so every Chinese string becomes mojibake and a mangled quote
    turns the whole file into a parse error - the window simply never opens, with no visible message. A
    .bat with Chinese in it has the same problem in cmd.exe.

    So: .ps1 with non-ASCII must start with a single UTF-8 BOM; .bat must be pure ASCII.
    """
    findings: list[str] = []
    for path in sorted(pathlib.Path(REPO).rglob("*")):
        if any(part in {".git", "build", "dist", ".tmp", "node_modules"} for part in path.parts):
            continue
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        if suffix not in {".ps1", ".bat"}:
            continue
        raw = path.read_bytes()
        rel = os.path.relpath(path, REPO)
        has_bom = raw.startswith(b"\xef\xbb\xbf")
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            findings.append(f"{rel}: not valid UTF-8")
            continue
        non_ascii = any(ord(ch) > 127 for ch in text)
        if suffix == ".ps1" and non_ascii and not has_bom:
            findings.append(f"{rel}: Chinese but no UTF-8 BOM - PowerShell 5.1 will misread it")
        if suffix == ".ps1" and raw.startswith(b"\xef\xbb\xbf\xef\xbb\xbf"):
            findings.append(f"{rel}: two BOMs")
        if suffix == ".bat" and non_ascii:
            findings.append(f"{rel}: .bat must be pure ASCII (cmd reads the OEM code page)")
    return findings

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

    findings.extend(check_script_encodings())
    findings.extend(check_baseline())

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
