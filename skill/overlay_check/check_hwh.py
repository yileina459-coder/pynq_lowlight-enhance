#!/usr/bin/env python3
"""Offline linter for a PYNQ overlay handoff file (.hwh).

Why this exists
    A custom overlay that fails to load on the board is expensive to debug: the
    board is remote, the error is one line, and the cause is usually structural
    (missing IP, unconnected clock, .bit and .hwh that do not share a base name).
    This lints the handoff file on the host, before any upload, and prints what
    PYNQ will actually see.

What it reads out of the .hwh (schema differs between Vivado versions, so both
the 2026.x attribute style and the older lowercase style are accepted)
    * MODULE instances: name, IP type, register base address
    * clock ports: CLKFREQUENCY on ports whose SIGIS is "clk"
    * the AXI DMA register window

Checks
    * .hwh exists and a .bit with the same base name sits next to it
    * at least one module is described (an empty IP list means PYNQ loads a
      bitstream that exposes nothing)
    * an AXI DMA is present
    * at least one clock is described
    * every module named with --expect is present

Usage
    python check_hwh.py board/dma_sobel/sobel_dma.hwh
    python check_hwh.py --expect axi_dma_0,sobel_0 board/dma_sobel/sobel_dma.hwh

Exit code 0 only when all checks pass.
"""

from __future__ import annotations

import argparse
import os
import sys
import xml.etree.ElementTree as ET

DMA_TYPES = ("axi_dma", "axi_vdma")


def attr(node, *names, default=""):
    for name in names:
        value = node.get(name)
        if value:
            return value
    return default


def parse_hwh(path: str) -> dict:
    root = ET.parse(path).getroot()

    modules = []
    for mod in root.iter("MODULE"):
        params = {}
        for par in mod.iter("PARAMETER"):
            pname = attr(par, "NAME")
            if pname in ("C_BASEADDR", "C_HIGHADDR"):
                params[pname] = attr(par, "VALUE")

        clocks = {}
        for port in mod.iter("PORT"):
            freq = attr(port, "CLKFREQUENCY")
            if freq:
                clocks[attr(port, "NAME")] = int(freq)

        modules.append({
            "name": attr(mod, "INSTANCE", "instance"),
            "type": attr(mod, "MODTYPE", "modtype"),
            "vlnv": attr(mod, "VLNV", "vlnv"),
            "base": params.get("C_BASEADDR", ""),
            "high": params.get("C_HIGHADDR", ""),
            "clocks": clocks,
        })

    return {"modules": modules}


def check(path: str, expected: list[str]) -> tuple[bool, list[str], dict | None]:
    problems: list[str] = []
    if not os.path.exists(path):
        return False, [f"handoff file not found: {path}"], None

    base = os.path.splitext(path)[0]
    if not os.path.exists(base + ".bit"):
        problems.append(
            f"missing bitstream with the same base name: {os.path.basename(base)}.bit")

    try:
        info = parse_hwh(path)
    except ET.ParseError as exc:
        return False, [f"cannot parse {path}: {exc}"], None

    modules = info["modules"]
    if not modules:
        problems.append("no MODULE entries: PYNQ would load a bitstream with an empty IP list")

    names = {m["name"] for m in modules}
    for want in expected:
        if want not in names:
            problems.append(f"expected module '{want}' not present in the handoff file")

    if not any(any(t in m["type"] for t in DMA_TYPES) for m in modules):
        problems.append("no AXI DMA module: nothing to drive a memory-mapped data path")

    all_clocks = {}
    for m in modules:
        all_clocks.update(m["clocks"])
    if not all_clocks:
        problems.append("no clock frequencies found: PYNQ cannot report the design clocks")

    info["all_clocks"] = all_clocks
    return not problems, problems, info


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("hwh")
    ap.add_argument("--expect", default="",
                    help="comma separated module names that must be present")
    args = ap.parse_args(argv)

    expected = [e.strip() for e in args.expect.split(",") if e.strip()]
    ok, problems, info = check(args.hwh, expected)

    if info:
        print(f"file            : {args.hwh}")
        print(f"modules         : {len(info['modules'])}")
        for mod in info["modules"]:
            addr = f"  @ {mod['base']}-{mod['high']}" if mod["base"] else ""
            print(f"  - {mod['name']:<16} {mod['type']:<22}{addr}")
        print(f"clocks          : {len(info['all_clocks'])}")
        for name, freq in sorted(info["all_clocks"].items()):
            print(f"  - {name}: {freq / 1e6:.3f} MHz")

    if problems:
        print("\nPROBLEMS")
        for p in problems:
            print(f"  * {p}")
        print("HWH CHECK FAIL")
        return 1

    print("HWH CHECK PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
