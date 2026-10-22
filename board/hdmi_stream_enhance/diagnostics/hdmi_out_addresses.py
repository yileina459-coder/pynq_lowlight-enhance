#!/usr/bin/env python3
"""Print the real base addresses and parameters of the output-side IPs.

Why not trust the addresses written by hand
    The probe read values that make no sense for axi_dynclk (a 1.4 THz "pixel clock"), which
    usually means the base address belongs to a different block. PYNQ already knows the addresses
    from the .hwh, so ask it - but only touch ip_dict, never attribute access, because reaching for
    ol.video would instantiate the video hierarchy and disturb the VDMA that the running demo owns.

    python3 hdmi_out_addresses.py
"""

from __future__ import annotations

from pynq import Overlay


def main() -> int:
    ol = Overlay("enhance_hdmi.bit")
    print(f"{'ip':<46}{'phys_addr':>14}{'type':>10}")
    for name, entry in sorted(ol.ip_dict.items()):
        low = name.lower()
        if not any(k in low for k in ("hpd", "dynclk", "vtc", "vdma")):
            continue
        addr = entry.get("phys_addr")
        addr_text = f"0x{addr:08x}" if addr is not None else "-"
        print(f"{name:<46}{addr_text:>14}{entry.get('type', ''):>10}")

    print()
    for name in ("video/hdmi_out/frontend/hdmi_out_hpd_video",
                 "video/hdmi_out/frontend/axi_dynclk",
                 "video/hdmi_out/frontend/vtc_out"):
        entry = ol.ip_dict.get(name)
        if entry is None:
            print(f"{name}: not in ip_dict")
            continue
        params = entry.get("parameters", {})
        keys = [k for k in params if any(s in k.upper()
                                         for s in ("ALL_INPUTS", "ALL_OUTPUTS", "TRI", "GPIO_WIDTH"))]
        if keys:
            for k in keys:
                print(f"{name}: {k} = {params[k]}")
        else:
            print(f"{name}: no GPIO configuration parameters exposed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
