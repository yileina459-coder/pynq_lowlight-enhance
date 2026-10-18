#!/usr/bin/env python3
"""Collect and summarise measurement data so the report never invents a number.

The rule this tool enforces: **every number in the report comes from a row in a
CSV that a script wrote.** No hand-typed tables, no "about 60 fps".

Schema (one row per measurement, append-only)
    timestamp | design | metric | value | unit | conditions | evidence

``design``      which implementation (e.g. ``pl_sobel_stream``, ``ps_numpy``)
``metric``      what was measured (e.g. ``frame_rate``, ``latency_p50``)
``conditions``  free text: resolution, tool version, clock, transfer size ...
``evidence``    path to the raw log / capture that backs this row

Usage
    python perf_collect.py --csv metrics.csv --record \
        --design pl_dma --metric frame_rate --value 57.2 --unit fps \
        --conditions "1280x720, 100 MHz, per-row DMA" --evidence board/log.txt

    python perf_collect.py --csv metrics.csv --summarize --out metrics.md
"""

from __future__ import annotations

import argparse
import csv
import os
import statistics
import sys
import time

FIELDS = ["timestamp", "design", "metric", "value", "unit", "conditions", "evidence"]


def record(path: str, design: str, metric: str, value: float, unit: str = "",
           conditions: str = "", evidence: str = "") -> None:
    write_header = not os.path.exists(path) or os.path.getsize(path) == 0
    with open(path, "a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        if write_header:
            writer.writeheader()
        writer.writerow({
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "design": design,
            "metric": metric,
            "value": value,
            "unit": unit,
            "conditions": conditions,
            "evidence": evidence,
        })


def read_rows(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def summarize(path: str) -> str:
    rows = read_rows(path)
    if not rows:
        return "_no measurements recorded yet_\n"

    groups: dict[tuple[str, str], list[tuple[float, str, str]]] = {}
    for r in rows:
        try:
            value = float(r["value"])
        except (KeyError, TypeError, ValueError):
            continue
        key = (r.get("design", ""), r.get("metric", ""))
        groups.setdefault(key, []).append(
            (value, r.get("unit", ""), r.get("conditions", "")))

    lines = ["| design | metric | n | mean | min | max | unit | conditions |",
             "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for (design, metric), values in sorted(groups.items()):
        nums = [v for v, _, _ in values]
        units = sorted({u for _, u, _ in values if u})
        conds = sorted({c for _, _, c in values if c})
        cond = "; ".join(conds)
        if len(cond) > 60:
            cond = cond[:57] + "..."
        lines.append(
            f"| {design} | {metric} | {len(nums)} | {statistics.mean(nums):.4g} | "
            f"{min(nums):.4g} | {max(nums):.4g} | {'/'.join(units)} | {cond} |")
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv", required=True, help="metrics CSV (created on first record)")
    ap.add_argument("--record", action="store_true", help="append one measurement")
    ap.add_argument("--design")
    ap.add_argument("--metric")
    ap.add_argument("--value", type=float)
    ap.add_argument("--unit", default="")
    ap.add_argument("--conditions", default="")
    ap.add_argument("--evidence", default="")
    ap.add_argument("--summarize", action="store_true", help="print a markdown table")
    ap.add_argument("--out", help="write the markdown table here as well")
    args = ap.parse_args(argv)

    if args.record:
        missing = [n for n in ("design", "metric", "value") if getattr(args, n) is None]
        if missing:
            print(f"--record needs: {', '.join('--' + m for m in missing)}", file=sys.stderr)
            return 2
        record(args.csv, args.design, args.metric, args.value,
               args.unit, args.conditions, args.evidence)
        print(f"recorded {args.design}/{args.metric} = {args.value} {args.unit}".rstrip())

    if args.summarize:
        table = summarize(args.csv)
        print(table)
        if args.out:
            with open(args.out, "w", encoding="utf-8") as fh:
                fh.write(table)
            print(f"wrote {args.out}")

    if not args.record and not args.summarize:
        print(summarize(args.csv))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
