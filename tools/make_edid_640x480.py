"""Build a 640x480-only EDID.

What we just learned on the board
    640x480 works end to end: with the *stock* overlay, writeframe() returned
    immediately (the VDMA consumed a frame) and the capture card showed the picture.
    720p and 1080p never consumed a frame and never produced TMDS. So the output
    hardware is fine and the limit is the pixel clock - the PYNQ-Z2's HDMI ports are
    unbuffered, driven directly from the PL.

    Therefore the whole system has to run at 640x480@60 (25.175 MHz pixel clock,
    125.9 MHz serial), and the EDID must stop Windows from offering anything higher.

Why the established timings have to go too
    The stock EDIDs list 640x480, 800x600, 832x624, 1024x768 and 1152x870 in the
    established bitmap, plus 1080p and friends in the standard timing list. Windows
    picks the highest mode it can, so all of them have to be cleared - including the
    established ones, otherwise it would choose 1024x768.

    python tools/make_edid_640x480.py
"""

from __future__ import annotations

import os

SRC = ("build/overlay_hdmi_enhance/.work/tree/boards/ip/dvi2rgb_v1_7/src/"
       "720p_edid.data")
DST = "src/rtl/edid/edid_640x480.data"


def load(path: str) -> bytearray:
    out = bytearray()
    for line in open(path, encoding="utf-8"):
        bits = line.strip()
        if bits:
            out.append(int(bits, 2))
    return out


def save(path: str, data: bytes) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        for byte in data:
            fh.write(f"{byte:08b}\n")


def dtd_640x480() -> bytes:
    """Detailed timing descriptor for 640x480@60 (25.175 MHz, standard VESA)."""
    pix_clk = 2517          # in 10 kHz units -> 25.17 MHz
    hact, hblank = 640, 160
    hsync_off, hsync_w = 16, 96
    vact, vblank = 480, 45
    vsync_off, vsync_w = 10, 2
    htotal, vtotal = hact + hblank, vact + vblank

    d = bytearray(18)
    d[0] = pix_clk & 0xFF
    d[1] = pix_clk >> 8
    d[2] = hact & 0xFF
    d[3] = hblank & 0xFF
    d[4] = ((hact >> 8) & 0x0F) << 4 | ((hblank >> 8) & 0x0F)
    d[5] = vact & 0xFF
    d[6] = vblank & 0xFF
    d[7] = ((vact >> 8) & 0x0F) << 4 | ((vblank >> 8) & 0x0F)
    d[8] = hsync_off & 0xFF
    d[9] = hsync_w & 0xFF
    d[10] = ((vsync_off & 0x0F) << 4) | (vsync_w & 0x0F)
    d[11] = 0x00            # no interlace, no stereo
    d[12] = ((htotal >> 8) & 0x0F) << 4 | ((vtotal >> 8) & 0x0F)
    d[13] = htotal & 0xFF
    d[14] = vtotal & 0xFF
    d[15] = 0x00
    d[16] = 0x00
    d[17] = 0x00
    # 0x1E = "digital separate" sync with +H +V, which is what 640x480@60 uses.
    d[17] = 0x1E
    return bytes(d)


def main() -> int:
    raw = load(SRC)

    # Established timings: leave only 640x480@60 (bit 2 of byte 35).
    raw[35] = 0x04
    raw[36] = 0x00
    raw[37] = 0x00

    # Standard timings: all unused.
    for i in range(8):
        raw[38 + i * 2] = 0x01
        raw[39 + i * 2] = 0x01

    # Preferred detailed timing (slot 1) -> 640x480@60.
    raw[54:72] = dtd_640x480()

    # Recompute the block checksum.
    raw[127] = 0
    raw[127] = (-sum(raw[:128])) & 0xFF

    save(DST, raw)

    pix = (raw[54] | (raw[55] << 8)) * 10
    hact = raw[56] | ((raw[58] & 0xF0) << 4)
    vact = raw[59] | ((raw[61] & 0xF0) << 4)
    htotal = (raw[56] | ((raw[58] & 0xF0) << 4)) + (raw[57] | ((raw[58] & 0x0F) << 8))
    vtotal = (raw[59] | ((raw[61] & 0xF0) << 4)) + (raw[60] | ((raw[61] & 0x0F) << 8))
    refresh = pix * 1000 / (htotal * vtotal) if htotal and vtotal else 0
    print(f"wrote {DST}")
    print(f"  preferred {hact}x{vact} at {pix / 1000:.2f} MHz, "
          f"total {htotal}x{vtotal} -> {refresh:.1f} Hz")
    print(f"  checksum {sum(raw) & 0xFF} (must be 0)")
    print(f"  established 0x{raw[35]:02x} 0x{raw[36]:02x} 0x{raw[37]:02x}")
    print("  standard timings cleared: no mode above 640x480 is advertised")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
