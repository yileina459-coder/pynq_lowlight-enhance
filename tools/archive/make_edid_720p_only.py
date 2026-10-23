"""Build a 720p-only EDID and verify it.

Why
    The stock 720p EDID also lists 1920x1080@60 in its standard timings, and Windows
    always picks the highest resolution - so the source keeps sending 1080p whatever
    was chosen before. On this board 1080p cannot work: with the PLL settings PYNQ
    ships, 148.5 MHz needs a VCO that is outside the Artix-7 -1 range, and the output
    emits no TMDS at all.

    720p60 (74.25 MHz) is the one mode where both the input and the output PLL are
    comfortably inside range, and it is already the EDID's preferred detailed timing.
    So: keep the detailed timing, clear the standard timing list (which is where 1080p
    comes from), recompute the checksum. Windows then has nothing higher to choose.

    python tools/archive/make_edid_720p_only.py [--check]
"""

from __future__ import annotations

import argparse
import os

SRC = ("build/overlay_hdmi_enhance/.work/tree/boards/ip/dvi2rgb_v1_7/src/"
       "720p_edid.data")
DST = "src/rtl/edid/720p_only_edid.data"


def load(path: str) -> bytearray:
    out = bytearray()
    for lineno, line in enumerate(open(path, encoding="utf-8"), 1):
        bits = line.strip()
        if not bits:
            continue
        if len(bits) != 8 or any(c not in "01" for c in bits):
            raise SystemExit(f"{path}:{lineno}: expected 8 binary digits")
        out.append(int(bits, 2))
    return out


def save(path: str, data: bytes) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        for byte in data:
            fh.write(f"{byte:08b}\n")


def describe(raw: bytes) -> str:
    pix = (raw[54] | (raw[55] << 8)) * 10
    hact = raw[56] | ((raw[58] & 0xF0) << 4)
    vact = raw[59] | ((raw[61] & 0xF0) << 4)
    total = sum(raw[:128]) & 0xFF
    return (f"preferred {hact}x{vact} at {pix / 1000:.2f} MHz, "
            f"checksum {'OK' if total == 0 else 'BAD'} ({total})")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true",
                    help="only report what is there, do not write")
    args = ap.parse_args(argv)

    raw = load(SRC)
    print(f"source {SRC}: {describe(raw)}")

    for i in range(8):
        offset = 38 + i * 2
        tag = (raw[offset] << 8) | raw[offset + 1]
        if tag not in (0x0101, 0x0000):
            w = (raw[offset] + 31) * 8
            print(f"  standard timing {i}: first byte 0x{raw[offset]:02x} "
                  f"(>= {w} px wide)")

    if args.check:
        return 0

    # Clear every standard timing slot. 0x01 0x01 is the "unused" encoding.
    for i in range(8):
        raw[38 + i * 2] = 0x01
        raw[39 + i * 2] = 0x01

    # Recompute the block checksum.
    raw[127] = 0
    raw[127] = (-sum(raw[:128])) & 0xFF

    save(DST, raw)
    print(f"\nwrote {DST}")
    print(f"  {describe(raw)}")
    print("  standard timings cleared, so no resolution above 1280x720 is advertised")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
