#!/usr/bin/env python3
"""Static checks on axis_sof_gen, aimed at the mistakes that actually happened.

Why a static check
    The first version failed implementation with

        [Opt 31-67] A LUT4 cell in the design is missing a connection on input pin I3 ...
        LUT cell name is base_i/sof_gen_0/inst/sof_i_4

    because `line == LINES - 1` compared a 9-bit counter against an untyped 32-bit constant. That
    costs a full synthesis+implementation cycle (about 35 minutes) to discover, so it is worth
    catching from the source instead.

    The check also asserts the two structural properties the fix depends on: TUSER must be driven
    by the SOF register (not passed through from upstream), and the data path must stay
    combinational so inserting the module cannot change the measured latency.

    python tools/check_sof_gen.py
"""

from __future__ import annotations

import re
import sys

PATH = "src/rtl/axis_sof_gen/axis_sof_gen.v"


def main() -> int:
    src = open(PATH, encoding="utf-8").read()
    problems = []

    # 1) The comparison must be same-width: a sized localparam plus a sized compare.
    if not re.search(r"localparam\s*\[[^\]]+\]\s*LAST_LINE", src):
        problems.append("LAST_LINE is not declared with an explicit width")
    if re.search(r"line\s*==\s*LINES\s*-\s*1", src):
        problems.append("comparison against the untyped LINES-1 is back (the Opt 31-67 trap)")
    if not re.search(r"line\s*==\s*LAST_LINE", src):
        problems.append("comparison does not use LAST_LINE")

    # 2) TUSER must be the SOF register, not a passthrough of the upstream value.
    if not re.search(r"assign\s+m_tuser\s*=\s*sof\s*;", src):
        problems.append("m_tuser is not driven by the sof register")
    if re.search(r"assign\s+m_tuser\s*=\s*s_tuser", src):
        problems.append("m_tuser is passed through from upstream (no SOF would be generated)")

    # 3) Data path must stay combinational so latency is unchanged.
    for port in ("m_tdata", "m_tvalid", "m_tlast"):
        if not re.search(rf"assign\s+{port}\s*=\s*s_", src):
            problems.append(f"{port} is not a straight combinational assignment")

    # 4) s_tready must come from m_tready, and the beat condition must use it.
    if not re.search(r"assign\s+s_tready\s*=\s*m_tready\s*;", src):
        problems.append("s_tready does not follow m_tready")
    if "s_tvalid & m_tready" not in src:
        problems.append("the beat condition does not use s_tvalid & m_tready - a counter that "
                        "advances on a stalled beat would lose frame alignment")

    # 5) Reset must clear both the counter and the SOF flag.
    reset_block = src[src.find("always @(posedge aclk)"):]
    if "if (!aresetn)" not in reset_block:
        problems.append("no reset branch in the sequential block")
    if "sof  <= 1'b1" not in reset_block and "sof <= 1'b1" not in reset_block:
        problems.append("reset does not assert SOF, so the first frame would be unaligned")

    if problems:
        print("SOF GEN CHECK FAIL")
        for p in problems:
            print("  -", p)
        return 1

    lines = re.search(r"localparam integer LINES\s*=\s*(\d+)", src)
    width = re.search(r"localparam integer LINE_BITS\s*=\s*(\d+)", src)
    print("SOF GEN CHECK PASS")
    if lines and width:
        need = (int(lines.group(1)) - 1).bit_length()
        have = int(width.group(1))
        print(f"  LINES={lines.group(1)} needs {need} bits, LINE_BITS={have}"
              f"{' (ok)' if have >= need else ' (TOO SMALL)'}")
        if have < need:
            return 1
    print("  tuser driven by the SOF register, data path combinational, "
          "reset asserts SOF, counter advances only on completed beats")
    return 0


if __name__ == "__main__":
    sys.exit(main())
