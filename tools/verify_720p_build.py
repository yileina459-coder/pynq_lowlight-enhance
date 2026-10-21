"""Confirm the 720p pinning reached the generated hardware.

Checks the generated wrappers (what actually gets synthesised) plus the embedded EDID,
so a silently-ignored BD property cannot waste another board test.
"""

from __future__ import annotations

import os
import re

GEN = "build/overlay_hdmi_enhance/.work/tree/boards/Pynq-Z2/base/base/base.gen"
EDID_TREE = ("build/overlay_hdmi_enhance/.work/tree/boards/ip/dvi2rgb_v1_7/src/"
             "720p_edid.data")


def find(name: str) -> str | None:
    for dirpath, _dirs, files in os.walk(GEN):
        if name in files:
            return os.path.join(dirpath, name)
    return None


def main() -> int:
    ok = True
    for wrapper, want in (("base_dvi2rgb_0_0.vhd", 2), ("base_rgb2dvi_0_0.vhd", 2)):
        path = find(wrapper)
        if path is None:
            print(f"{wrapper}: not found")
            ok = False
            continue
        text = open(path, encoding="utf-8", errors="replace").read()
        m = re.search(r"kClkRange\s*=>\s*(\d+)", text)
        got = int(m.group(1)) if m else None
        verdict = "OK" if got == want else "WRONG"
        print(f"{wrapper}: kClkRange => {got} (want {want}) {verdict}")
        ok &= got == want

    print()
    raw = bytearray()
    for line in open(EDID_TREE, encoding="utf-8"):
        bits = line.strip()
        if bits:
            raw.append(int(bits, 2))
    pix = (raw[54] | (raw[55] << 8)) * 10
    hact = raw[56] | ((raw[58] & 0xF0) << 4)
    vact = raw[59] | ((raw[61] & 0xF0) << 4)
    checksum = sum(raw) & 0xFF
    std = [(raw[38 + i * 2], raw[39 + i * 2]) for i in range(8)]
    has_1080 = any((b1 << 8 | b2) not in (0x0101, 0x0000) and (b1 + 31) * 8 >= 1920
                   for b1, b2 in std)
    print(f"EDID in tree: preferred {hact}x{vact} at {pix / 1000:.2f} MHz, "
          f"checksum {'OK' if checksum == 0 else 'BAD'}")
    print(f"  advertises anything >= 1920 wide: {has_1080} "
          f"({'BAD' if has_1080 else 'OK - Windows cannot pick 1080p'})")
    ok &= checksum == 0 and not has_1080 and (hact, vact) == (1280, 720)

    print()
    print("BUILD VERIFIED" if ok else "BUILD NOT AS INTENDED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
