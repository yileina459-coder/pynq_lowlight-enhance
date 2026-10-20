"""Validate the EDID that the PYNQ presents on its HDMI input.

Why this matters
    HPD + a readable EDID is enough for Windows to *enumerate* a monitor, but not
    enough for the GPU to start driving TMDS. A bad checksum, a malformed preferred
    timing, or an advertised mode the driver refuses all produce our exact symptom:
    a monitor appears in Device Manager, no picture comes out, and the FPGA's input
    PLL reports no lock because there is nothing to lock onto.

File format (this is what bit us first)
    dvi2rgb's ``kEdidFileName`` is not a binary .bin: it is one byte per line as
    eight ASCII binary digits, because the IP reads it into a std_logic_vector
    initialisation. Reading it as binary yields nonsense, which is how the first
    version of this script wrongly reported "EDID INVALID".

    python tools/check_edid.py [path]
"""

from __future__ import annotations

import sys

DEFAULT = ("build/overlay_hdmi_enhance/.work/tree/boards/ip/dvi2rgb_v1_7/src/"
           "720p_edid.data")


def load(path: str) -> bytes:
    out = bytearray()
    for lineno, line in enumerate(open(path, encoding="utf-8"), 1):
        bits = line.strip()
        if not bits:
            continue
        if len(bits) != 8 or any(c not in "01" for c in bits):
            raise SystemExit(f"{path}:{lineno}: expected 8 binary digits, got {bits!r}")
        out.append(int(bits, 2))
    return bytes(out)


def main(argv=None) -> int:
    path = (argv or sys.argv[1:] or [DEFAULT])[0]
    raw = load(path)
    print(f"{path}: {len(raw)} bytes")

    ok_header = raw[:8] == bytes([0x00, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0x00])
    print(f"header      : {'OK' if ok_header else 'BAD'} ({raw[:8].hex(' ')})")

    blocks = len(raw) // 128
    checks_ok = True
    for b in range(blocks):
        chunk = raw[b * 128:(b + 1) * 128]
        total = sum(chunk) & 0xFF
        checks_ok &= total == 0
        print(f"block {b}     : checksum 0x{chunk[127]:02x}, sum mod 256 = {total} "
              f"{'OK' if total == 0 else 'BAD'}")

    vid = (raw[8] << 8) | raw[9]
    print(f"manufacturer: {(vid >> 10) & 0x1F}{chr(((vid >> 5) & 0x1F) + 64)}"
          f"{chr((vid & 0x1F) + 64)}   product 0x{raw[10] | (raw[11] << 8):04x}")
    print(f"EDID version: {raw[18]}.{raw[19]}")

    dtd = raw[54:72]
    pix_clk_khz = (dtd[0] | (dtd[1] << 8)) * 10
    hact = dtd[2] | ((dtd[4] & 0xF0) << 4)
    hblank = dtd[3] | ((dtd[4] & 0x0F) << 8)
    vact = dtd[5] | ((dtd[7] & 0xF0) << 4)
    vblank = dtd[6] | ((dtd[7] & 0x0F) << 8)
    htotal, vtotal = hact + hblank, vact + vblank
    if pix_clk_khz and htotal and vtotal:
        refresh = pix_clk_khz * 1000 / (htotal * vtotal)
        print(f"preferred   : {hact}x{vact} @ {refresh:.1f} Hz, "
              f"pixel clock {pix_clk_khz / 1000:.2f} MHz, total {htotal}x{vtotal}")
        print(f"  TMDS clock: {pix_clk_khz / 2000:.2f} MHz")
        # For the dvi2rgb MMCM: FVCO = TMDS * MULT_F must be 600-1200 MHz.
        tmds = pix_clk_khz / 2000
        for k in (1, 2, 3):
            fvco = tmds * 5 * k
            verdict = "valid" if 600 <= fvco <= 1200 else "OUT OF RANGE"
            print(f"  kClkRange={k}: MULT_F={5 * k}, FVCO={fvco:.1f} MHz -> {verdict}")
    else:
        print("preferred   : could not parse the detailed timing")

    for i, offset in enumerate((72, 90, 108), start=2):
        d = raw[offset:offset + 18]
        if d[0] == 0 and d[1] == 0 and d[3] == 0x10:
            print(f"descriptor {i}: name {d[5:18].decode('ascii', 'replace').strip(chr(0) + ' ') !r}")
        elif d[0] == 0 and d[1] == 0 and d[3] == 0xFD:
            print(f"descriptor {i}: range limits")
        else:
            print(f"descriptor {i}: {d.hex(' ')}")

    ok = ok_header and checks_ok and blocks >= 1
    print()
    print("EDID VALID" if ok else "EDID INVALID - this alone would explain no TMDS")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
