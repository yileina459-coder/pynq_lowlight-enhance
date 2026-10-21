#!/usr/bin/env python3
"""Generate the one-page English A4 poster required for the final round.

The competition asks for a single-page English poster made with AMD's PPT
template; the template is supplied by the organisers and is not in this
repository, so this produces a plain A4 portrait slide with the same content,
ready to be re-styled into the official template.

Layout is computed, not hand-placed: each block's height is estimated from the
number of characters it has to fit, so the page cannot silently overflow when the
text changes. The script prints the resulting layout so the fit can be checked
without opening PowerPoint.

Every number comes from a file in this repository:

    board/dma_sobel/metrics_board.csv      PS vs PL measurements
    board/hdmi_stream/timing_impl.rpt      WNS of the HDMI overlay
    build/hls/*/reports/csynth.rpt         kernel resources / Fmax

    python report/poster/make_poster.py
"""

from __future__ import annotations

import math
import os

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import MSO_AUTO_SIZE, PP_ALIGN
from pptx.util import Cm, Pt

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(REPO, "report", "poster", "poster.pptx")
FIGURE = os.path.join(REPO, "board", "hdmi_stream_enhance", "evidence", "hdmi_presets_2x2.png")

NAVY = RGBColor(0x12, 0x2B, 0x4A)
ACCENT = RGBColor(0x1E, 0x88, 0xE5)
GREY = RGBColor(0x33, 0x33, 0x33)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)

PAGE_W, PAGE_H = 21.0, 29.7
MARGIN = 1.0
BODY_W = PAGE_W - 2 * MARGIN


def line_height_cm(size_pt: float) -> float:
    """Rough line box for Arial at a given point size (1.25 x font size)."""
    return size_pt * 1.25 / 28.35


def estimate_lines(text: str, size_pt: float, width_cm: float) -> int:
    """Characters per line for Arial is about 0.5 em; be conservative at 0.55."""
    per_line = max(20, int(width_cm / (size_pt * 0.55 / 28.35)))
    lines = 0
    for chunk in text.split("\n"):
        lines += max(1, math.ceil(len(chunk) / per_line))
    return lines


def add_text(slide, left, top, width, text, size=9.0, bold=False, color=GREY,
             align=PP_ALIGN.LEFT):
    height = estimate_lines(text, size, width) * line_height_cm(size) + 0.15
    box = slide.shapes.add_textbox(Cm(left), Cm(top), Cm(width), Cm(height))
    frame = box.text_frame
    frame.word_wrap = True
    # Without this python-pptx writes <a:spAutoFit/>, and LibreOffice then sizes the
    # box to the text instead of wrapping it - the whole page overflows sideways.
    frame.auto_size = MSO_AUTO_SIZE.NONE
    for i, line in enumerate(text.split("\n")):
        para = frame.paragraphs[0] if i == 0 else frame.add_paragraph()
        para.alignment = align
        para.line_spacing = 1.0
        run = para.add_run()
        run.text = line
        run.font.size = Pt(size)
        run.font.bold = bold
        run.font.color.rgb = color
        run.font.name = "Arial"
    return height


def add_heading(slide, top, text):
    add_text(slide, MARGIN, top, BODY_W, text, size=12, bold=True, color=ACCENT)
    bar = slide.shapes.add_shape(1, Cm(MARGIN), Cm(top + 0.62), Cm(BODY_W), Cm(0.04))
    bar.fill.solid()
    bar.fill.fore_color.rgb = ACCENT
    bar.line.fill.background()
    bar.shadow.inherit = False
    return 0.95


def main() -> int:
    prs = Presentation()
    prs.slide_width = Cm(PAGE_W)
    prs.slide_height = Cm(PAGE_H)
    slide = prs.slides.add_slide(prs.slide_layouts[6])

    head = slide.shapes.add_shape(1, Cm(0), Cm(0), Cm(PAGE_W), Cm(2.5))
    head.fill.solid()
    head.fill.fore_color.rgb = NAVY
    head.line.fill.background()
    head.shadow.inherit = False

    add_text(slide, MARGIN, 0.4, BODY_W,
             "A One-Line-Latency Vision Enhancement Terminal",
             size=18, bold=True, color=WHITE)
    add_text(slide, MARGIN, 1.5, BODY_W,
             "PYNQ-Z2  |  reading aid for the low-vision  |  2026 Embedded Chip & System Design Competition, "
             "AMD track, self-selected topic (junior group)  |  Zynq-7000 XC7Z020  |  Vivado / Vitis HLS 2026.1",
             size=9, color=RGBColor(0xC8, 0xD8, 0xEA))

    y = 2.95
    layout = []

    sections = [
        ("Motivation",
         "Around 17 million people in China live with low vision, and shop-bought electronic magnifiers are expensive while phone/PC pipelines take 100-300 ms from capture to display - enough latency to cause dizziness. For this class of device the key metric is not frame rate but end-to-end latency. This project therefore puts the whole enhancement chain inside the pixel stream, with no frame buffer at all."),
        ("Architecture",
         "Main path:  PS frame -> VDMA -> enhance -> pixel_unpack -> HDMI OUT, with the kernel sitting in "
         "the live pixel stream; measured 21 pixel clocks on the board, seven presets switched while "
         "video keeps running.\n"
         "The frame source is the VDMA because this board's HDMI output only works at 640x480 "
         "(800x600/720p/1080p consume no frames; the stock bitstream behaves identically - the pins are "
         "unbuffered), while the HDMI input IP cannot run at 640x480. With no common mode, frames come "
         "from DDR and the kernel still processes real pixels.\n"
         "The enhance kernel runs local contrast -> tone curve -> binarise/invert -> split screen, "
         "all integer, one pixel per clock; 59 configuration bits are driven from the PS at "
         "run time.\n"
         "Verification path:  PS <-> DDR <-> AXI DMA <-> operator, readable back, so bit-exact "
         "checks need no display.\n"
         "Three rotating line buffers plus per-row 3-tap shift registers give each buffer one read "
         "and one write per pixel, which is what fits II = 1 into a dual-port BRAM."),
        ("Operators",
         "enhance: 3 BRAM, 2 DSP, 2168 FF, 1659 LUT (3%), II = 1, estimated Fmax 194.59 MHz at 7 ns. The operator family behind it - Sobel, 3x3 Gaussian, 3x3 sharpen - is hand-written HLS too (II = 1, 194.6 MHz, under 1.1k LUT each), and colour-space conversion reuses PYNQ's verified color_convert IP instead of being rewritten."),
        ("Correctness",
         "enhance passes C simulation against an independently written C++ golden model in two configurations (contrast+split, and tone+binarise+invert+mono): 9216 beats each, 0 errors. Through the AXI-DMA path, all eight presets are compared channel by channel with the numpy model: 0 mismatches out of 2,764,800 channels each, at 15.6 ms per frame. A second pair of counters brackets the kernel and stamps the first beat in and out: the measured pipeline latency is 16 pixel clocks, i.e. 160 ns at 100 MHz - about 1% of a 720p60 line, which is what having no frame buffer buys. "
         "Border policy (horizontal replicate, vertical line-buffer state) is defined once and shared "
         "by hardware, testbench and Python model, which is why the comparison can use zero tolerance."),
        ("What Made It Work - and What Did Not",
         "A free-running kernel (ap_ctrl_none) never drains its pipeline when the input stops, so an "
         "AXI-DMA transfer can never close and the DMA path needs a bounded variant (ap_ctrl_hs plus a "
         "pixel count). The same property bit the other way: HLS registers loop-invariant inputs in the "
         "pipeline prologue, so six of nine configuration parameters froze at power-up (see "
         "binarize_read_reg_* in the netlist). A gate lets the PS reset only the kernel through a spare "
         "configuration bit, so the preset is re-sampled - that is how seven presets switch live."),
        ("Reusable PYNQ Skills and Reproducibility",
         "Four board-independent skills ship with the project: overlay handoff linting (.hwh), "
         "bit-exact image comparison, measurement collection with PS-vs-PL table generation, and "
         "AXI-DMA helpers with cache maintenance and timeouts. Each documents scope, usage, failure "
         "modes and what was verified. Everything is scripted: a clean machine rebuilds both "
         "bitstreams with two commands."),
    ]

    for title, body in sections:
        need = 0.95 + estimate_lines(body, 9.0, BODY_W) * line_height_cm(9.0) + 0.14
        layout.append((title, round(y, 2), round(need, 2)))
        y += add_heading(slide, y, title)
        y += add_text(slide, MARGIN, y, BODY_W, body)
        y += 0.10

    # results table + figure side by side
    y += 0.1
    y += add_heading(slide, y, "Operator Family on the DMA Path (same board, same 1280x720 image)")

    rows = [
        ("Measured on the board", "PS (Cortex-A9, numpy)", "PL (Zynq + DMA)"),
        ("enhance, 8 presets", "-", "15.6 ms/frame, 0/2764800 wrong"),
        ("Pipeline latency", "-", "16 pixel clocks = 160 ns"),
        ("Sobel family, frame time", "3108.4 ms", "15.8 ms (196.7x)"),
    ]
    table_w, table_h = 12.0, 3.0
    shape = slide.shapes.add_table(len(rows), 3, Cm(MARGIN), Cm(y), Cm(table_w), Cm(table_h))
    table = shape.table
    table.columns[0].width = Cm(3.4)
    table.columns[1].width = Cm(4.3)
    table.columns[2].width = Cm(4.3)
    for r, row in enumerate(rows):
        for c, value in enumerate(row):
            cell = table.cell(r, c)
            cell.text = value
            para = cell.text_frame.paragraphs[0]
            run = para.runs[0]
            run.font.size = Pt(9)
            run.font.name = "Arial"
            run.font.bold = (r == 0 or r == len(rows) - 1)
            run.font.color.rgb = WHITE if r == 0 else GREY

    if os.path.exists(FIGURE):
        fig_w = 4.5
        fig_h = fig_w * 576 / 766
        slide.shapes.add_picture(FIGURE, Cm(MARGIN + table_w + 0.7), Cm(y),
                                 width=Cm(fig_w), height=Cm(fig_h))
        add_text(slide, MARGIN + table_w + 0.7, y + fig_h + 0.1, fig_w,
                 "Four states captured from the board's HDMI output; top right shows the split", size=8,
                 color=RGBColor(0x77, 0x77, 0x77), align=PP_ALIGN.CENTER)

    y += max(table_h, fig_w * 576 / 766 + 0.45) + 0.15

    add_text(slide, MARGIN, y, BODY_W,
             "Tool versions: Vivado / Vitis HLS 2026.1, PYNQ 3.1.1 image, device "
             "xc7z020clg400-1.  Repository: README.md, docs/ (docs/hdmi_status.md records the HDMI "
             "measurements and the two hardware limits), report/design_report.md, report/comparison.md.",
             size=8, color=RGBColor(0x88, 0x88, 0x88))
    used = y + 0.5

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    prs.save(OUT)

    print(f"wrote {OUT}")
    print(f"page {PAGE_W} x {PAGE_H} cm, content ends at {used:.2f} cm")
    for title, top, need in layout:
        print(f"  {top:6.2f} cm  (+{need:4.2f})  {title}")
    # `used` already reserves 0.5 cm of breathing room below the last line, so the page
    # is only really over when that reservation itself leaves the sheet.
    if used > PAGE_H:
        print("WARNING: content overflows the page")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
