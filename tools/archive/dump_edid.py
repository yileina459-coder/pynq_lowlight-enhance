"""Dump every field of the 720p EDID so we can see why Windows prefers 1080p.

The detailed timing descriptor says 1280x720, yet Windows keeps selecting 1920x1080.
That can only come from the other descriptors: the established timings bitmap, the
standard timings list, or a range-limits descriptor whose maximum pixel clock leaves
room for 1080p. Printing all of them settles it.

    python tools/archive/dump_edid.py [path]
"""

from __future__ import annotations

import sys

DEFAULT = ("build/overlay_hdmi_enhance/.work/tree/boards/ip/dvi2rgb_v1_7/src/"
           "720p_edid.data")

# Byte 35 established timings, bit -> mode
ESTABLISHED = [
    (0, 31, "720x400@70"),
    (1, 31, "720x400@88"),
    (2, 31, "640x480@60"),
    (3, 31, "640x480@67"),
    (4, 31, "640x480@72"),
    (5, 31, "640x480@75"),
    (6, 31, "800x600@56"),
    (7, 31, "800x600@60"),
    (0, 34, "800x600@72"),
    (1, 34, "800x600@75"),
    (2, 34, "832x624@75"),
    (3, 34, "1024x768@87i"),
    (4, 34, "1024x768@60"),
    (5, 34, "1024x768@70"),
    (6, 34, "1024x768@75"),
    (7, 34, "1280x1024@75"),
    (0, 35, "1152x870@75"),
]


def load(path: str) -> bytes:
    out = bytearray()
    for lineno, line in enumerate(open(path, encoding="utf-8"), 1):
        bits = line.strip()
        if not bits:
            continue
        if len(bits) != 8 or any(c not in "01" for c in bits):
            raise SystemExit(f"{path}:{lineno}: expected 8 binary digits")
        out.append(int(bits, 2))
    return bytes(out)


def standard_timing(b1: int, b2: int) -> str:
    if (b1, b2) == (0x01, 0x01):
        return "unused"
    w = (b1 + 31) * 8
    aspect = {0: "16:10", 1: "4:3", 2: "5:4", 3: "16:9"}[(b2 >> 6) & 0x03]
    rate = (b2 & 0x3F) + 60
    h, v = {
        "16:10": (w, w * 10 // 16),
        "4:3": (w, w * 3 // 4),
        "5:4": (w, w * 4 // 5),
        "16:9": (w, w * 9 // 16),
    }[aspect]
    return f"{h}x{v}@{rate} (aspect {aspect})"


def main(argv=None) -> int:
    path = (argv or sys.argv[1:] or [DEFAULT])[0]
    raw = load(path)
    print(f"{path}: {len(raw)} bytes\n")

    print(f"version {raw[18]}.{raw[19]}, input type byte 0x{raw[20]:02x} "
          f"({'digital' if raw[20] & 0x80 else 'analog'})")
    print(f"screen size {raw[21]} x {raw[22]} cm, gamma 0x{raw[23]:02x}")

    print("\nestablished timings:")
    any_est = False
    for bit, byte_index, name in ESTABLISHED:
        if raw[byte_index] & (1 << bit):
            print(f"  {name}")
            any_est = True
    if not any_est:
        print("  (none)")

    print("\nstandard timings:")
    for i in range(8):
        b1, b2 = raw[38 + i * 2], raw[39 + i * 2]
        print(f"  {i}: {standard_timing(b1, b2)}")

    print("\ndescriptors:")
    for i, offset in enumerate((54, 72, 90, 108), start=1):
        d = raw[offset:offset + 18]
        if d[0] or d[1]:
            pix = (d[0] | (d[1] << 8)) * 10
            hact = d[2] | ((d[4] & 0xF0) << 4)
            vact = d[5] | ((d[7] & 0xF0) << 4)
            print(f"  {i}: detailed timing {hact}x{vact} @ {pix / 1000:.2f} MHz")
            continue
        tag = d[3]
        if tag == 0xFC:
            print(f"  {i}: monitor name {d[5:18].decode('ascii', 'replace').strip(chr(0) + ' ')!r}")
        elif tag == 0xFD:
            min_v, max_v = d[5], d[6]
            min_h, max_h = d[7], d[8]
            max_pix = d[9] * 10
            print(f"  {i}: range limits V {min_v}-{max_v} Hz, H {min_h}-{max_h} kHz, "
                  f"max pixel clock {max_pix} MHz")
        elif tag == 0xFF:
            print(f"  {i}: serial {d[5:18].decode('ascii', 'replace').strip(chr(0) + ' ')!r}")
        elif tag == 0xFE:
            print(f"  {i}: ASCII text {d[5:18].decode('ascii', 'replace').strip(chr(0) + ' ')!r}")
        elif tag == 0x10:
            print(f"  {i}: dummy")
        else:
            print(f"  {i}: tag 0x{tag:02x}  {d.hex(' ')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
