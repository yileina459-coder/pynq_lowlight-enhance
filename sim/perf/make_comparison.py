#!/usr/bin/env python3
"""Turn the metrics CSV into the PS-vs-PL comparison table the report needs.

The scoring rubric gives 20 points to "performance and resource optimisation"
and expects a comparison table between a pure-software implementation and the
hardware one. That table should not be typed by hand: it is derived here from
the same CSV that ``skill/perf_collect`` writes, so every cell traces back to a
logged run.

Usage
    python sim/perf/make_comparison.py --csv metrics.csv --out report/comparison.md
    python sim/perf/make_comparison.py --csv metrics.csv --design-a ps_ --design-b pl_

``--design-a`` / ``--design-b`` are prefixes used to classify rows into the
software and hardware columns.
"""

from __future__ import annotations

import argparse
import csv
import statistics
import sys
from collections import defaultdict

# Metrics where a smaller number is better. Everything else is treated as a
# throughput-like metric where bigger is better.
LOWER_IS_BETTER = {"frame_time_mean", "frame_time_p99", "latency", "latency_p50",
                   "latency_p99", "latency_max", "dma_time"}


def load(path: str) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def mean_by_design(rows: list[dict]) -> dict[str, dict[str, tuple[float, str]]]:
    """metric -> design -> (mean, unit)"""
    acc: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    units: dict[str, dict[str, str]] = defaultdict(dict)
    for r in rows:
        try:
            value = float(r["value"])
        except (KeyError, TypeError, ValueError):
            continue
        design = r.get("design", "")
        metric = r.get("metric", "")
        acc[metric][design].append(value)
        units[metric][design] = r.get("unit", "")

    out: dict[str, dict[str, tuple[float, str]]] = {}
    for metric, designs in acc.items():
        out[metric] = {d: (statistics.mean(v), units[metric][d])
                       for d, v in designs.items()}
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv", required=True)
    ap.add_argument("--out", help="write the markdown table here")
    ap.add_argument("--design-a", default="ps", help="prefix of the software rows")
    ap.add_argument("--design-b", default="pl", help="prefix of the hardware rows")
    args = ap.parse_args(argv)

    try:
        rows = load(args.csv)
    except OSError as exc:
        print(f"cannot read {args.csv}: {exc}", file=sys.stderr)
        return 2

    if not rows:
        print(f"{args.csv} has no measurements yet")
        return 1

    table = mean_by_design(rows)

    lines = ["| metric | software | hardware | speed-up | unit |",
             "| --- | --- | --- | --- | --- |"]
    for metric in sorted(table):
        designs = table[metric]
        soft = [v for d, (v, _) in designs.items() if d.startswith(args.design_a)]
        hard = [v for d, (v, _) in designs.items() if d.startswith(args.design_b)]
        unit = next(iter(designs.values()))[1]
        s = f"{statistics.mean(soft):.4g}" if soft else "-"
        h = f"{statistics.mean(hard):.4g}" if hard else "-"
        if soft and hard:
            sm, hm = statistics.mean(soft), statistics.mean(hard)
            if hm == 0:
                ratio = "inf"
            elif metric in LOWER_IS_BETTER:
                ratio = f"{sm / hm:.2f}x"
            else:
                ratio = f"{hm / sm:.2f}x"
        else:
            ratio = "-"
        lines.append(f"| {metric} | {s} | {h} | {ratio} | {unit} |")

    text = "\n".join(lines) + "\n"
    print(text)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text)
        print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
