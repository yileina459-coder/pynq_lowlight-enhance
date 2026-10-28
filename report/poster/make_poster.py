# -*- coding: utf-8 -*-
"""Two-page poster (Chinese + English) on the official 16:9 poster grid."""
import os
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
OUT = os.path.join(HERE, "poster.pptx")
PHOTO = os.path.join(ROOT, "report", "assets", "photos", "setup_full_view.jpg")

NAVY = RGBColor(0x0E, 0x2A, 0x47)
INK = RGBColor(0x1A, 0x1A, 0x1A)
GREY = RGBColor(0x55, 0x5F, 0x6B)
ACCENT = RGBColor(0x00, 0x8C, 0xC8)
LIGHT = RGBColor(0xF2, 0xF5, 0xF8)
RULE = RGBColor(0xD8, 0xE0, 0xE8)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
CN = "Microsoft YaHei"
EN = "Segoe UI"

prs = Presentation()
prs.slide_width = Inches(13.333)
prs.slide_height = Inches(7.5)
blank = prs.slide_layouts[6]


def box(slide, x, y, w, h, fill=None, line=None, shape=MSO_SHAPE.RECTANGLE, line_w=1.0):
    sh = slide.shapes.add_shape(shape, Inches(x), Inches(y), Inches(w), Inches(h))
    if fill is None:
        sh.fill.background()
    else:
        sh.fill.solid()
        sh.fill.fore_color.rgb = fill
    if line is None:
        sh.line.fill.background()
    else:
        sh.line.color.rgb = line
        sh.line.width = Pt(line_w)
    sh.shadow.inherit = False
    return sh


def text(slide, x, y, w, h, runs, size=12, color=INK, font=CN, bold=False,
         align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, spacing=1.0, space_after=0):
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = 0
    tf.margin_right = 0
    tf.margin_top = 0
    tf.margin_bottom = 0
    if isinstance(runs, str):
        runs = [runs]
    for i, line in enumerate(runs):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.line_spacing = spacing
        p.space_after = Pt(space_after)
        r = p.add_run()
        r.text = line
        r.font.size = Pt(size)
        r.font.bold = bold
        r.font.color.rgb = color
        r.font.name = font
    return tb


def header(slide, title, subtitle, tag, tsize=33):
    box(slide, 0, 0, 13.333, 1.22, fill=NAVY)
    text(slide, 0.55, 0.18, 9.9, 0.60, title, size=tsize, color=WHITE, bold=True)
    text(slide, 0.57, 0.80, 9.6, 0.30, subtitle, size=12.5, color=RGBColor(0xC8, 0xD6, 0xE2))
    text(slide, 9.90, 0.26, 3.0, 0.28, tag, size=11, color=RGBColor(0xC8, 0xD6, 0xE2),
         font=EN, align=PP_ALIGN.RIGHT)
    text(slide, 9.90, 0.58, 3.0, 0.28, "PYNQ-Z2 · XC7Z020 · Vitis HLS 2026.1", size=10,
         color=RGBColor(0x8F, 0xA6, 0xBC), font=EN, align=PP_ALIGN.RIGHT)


def section(slide, x, y, w, num, title, font):
    text(slide, x, y, w, 0.28, f"{num}  {title}", size=14, color=ACCENT, font=font, bold=True)
    box(slide, x, y + 0.31, w, 0.015, fill=RULE)


def bullets(slide, x, y, w, items, font, size=10.8, step=1.18):
    cy = y
    for head, body in items:
        text(slide, x, cy, w, 0.22, head, size=size + 0.6, color=INK, font=font, bold=True)
        text(slide, x, cy + 0.27, w, 0.48, body, size=size, color=GREY, font=font, spacing=1.12)
        cy += step
    return cy


def chip(slide, x, y, w, h, big, small, font):
    box(slide, x, y, w, h, fill=LIGHT)
    box(slide, x, y, 0.055, h, fill=ACCENT)
    text(slide, x + 0.15, y + 0.07, w - 0.20, 0.30, big, size=16.5, color=NAVY, bold=True)
    text(slide, x + 0.15, y + 0.40, w - 0.20, 0.26, small, size=8.2, color=GREY, font=font, spacing=1.05)


def arrow(slide, x1, y1, x2, y2):
    sh = slide.shapes.add_connector(1, Inches(x1), Inches(y1), Inches(x2), Inches(y2))
    sh.line.color.rgb = ACCENT
    sh.line.width = Pt(1.4)


def node(slide, x, y, w, h, label, font, size=8.5):
    sh = box(slide, x, y, w, h, fill=NAVY, shape=MSO_SHAPE.ROUNDED_RECTANGLE)
    tf = sh.text_frame
    tf.word_wrap = True
    tf.margin_left = Inches(0.03)
    tf.margin_right = Inches(0.03)
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    r = p.add_run()
    r.text = label
    r.font.size = Pt(size)
    r.font.bold = True
    r.font.color.rgb = WHITE
    r.font.name = font


CN_DATA = dict(
    tag="中文版",
    title="低延迟视觉增强终端",
    subtitle="面向低照度图像观察的 FPGA 像素流增强",
    intro=[
        ("问题", "低照度图像噪声大、对比度低；软件增强一帧 3.1 s，无法连续观察。"),
        ("思路", "把整条增强链放进 PL 像素通路，像素进多少出多少，延迟以时钟计而不是以帧计。"),
        ("目标", "不加帧缓存，同时做到画质可调、结果可复算、参数可在线切换。"),
        ("方法", "以逐位比对定正确性，以双时间戳定延迟，以寄存器写定切换。"),
    ],
    arch=[("主机浏览器", "PC"), ("DDR 帧缓冲", "PS"), ("VDMA", "AXI"),
          ("采集卡 / OBS", "主机"), ("HDMI 输出", "640×480"), ("增强核", "PL")],
    note="像素进多少出多少 · 链内无帧缓存",
    design=[
        ("三抽头行缓冲", "每行缓冲每周期只读一次，II 保持为 1，8 个算子共用同一套读口。"),
        ("参数存 BRAM", "10 档预设写入寄存器即生效，不复位、不中断像素流。"),
        ("全整数定点", "与 NumPy 黄金模型 0 容差比对，8 档 2,764,800 通道逐位一致。"),
        ("双时间戳", "DMA 与 HDMI 两条通路各自打点，实测流水线延迟 16 拍 / 160 ns。"),
    ],
    results=[("194.59 MHz", "实现后频率，WNS +0.206 ns"),
             ("1,659 LUT", "占 XC7Z020 的 3%；FF 2,168 / BRAM 3 / DSP 2"),
             ("15.6 ms", "1280×720 单帧处理时间"),
             ("196.7×", "相对 ARM 纯软件的加速比（Sobel）")],
    foot="照片：笔记本运行 OBS，经采集卡接收板卡 HDMI 输出。",
    band="复现：源码、构建脚本与黄金模型都在仓库，按 README 四步重建。   验证：8 档预设逐位 0 差异，双时间戳实测 16 / 21 拍。   边界：HDMI 固定 640×480@60，延迟指 PL 内部流水线。",
)

EN_DATA = dict(
    tag="English",
    tsize=25, bsize=9.4, dsize=7.6, dstep=0.44, dstep2=0.56, bstep=1.02,
    title="Low-Latency Vision Enhancement Terminal",
    subtitle="Pixel-stream enhancement on FPGA for low-light image observation",
    intro=[
        ("Problem", "Low-light images are noisy and flat; software enhancement takes 3.1 s per frame."),
        ("Approach", "The chain runs inside the PL pixel path: pixels in, pixels out, latency in clocks, not frames."),
        ("Goal", "Adjustable quality, reproducible results and live preset switching, no extra frame buffer."),
        ("Method", "Correctness by bit-exact compare, latency by dual timestamps, switching by one register write."),
    ],
    arch=[("Host browser", "PC"), ("DDR frame buffer", "PS"), ("VDMA", "AXI"),
          ("Capture / OBS", "host"), ("HDMI out", "640×480"), ("Enhance core", "PL")],
    note="pixels in, pixels out · no frame buffer in the chain",
    design=[
        ("Three-tap line buffer", "Each line buffer is read once per cycle, keeping II = 1 for all eight operators."),
        ("Parameters in BRAM", "Ten presets take effect on a register write, without reset or stream interruption."),
        ("Integer datapath", "Bit-exact against a NumPy golden model: 0 of 2,764,800 channels differ across 8 presets."),
        ("Dual timestamps", "DMA and HDMI paths are timed separately; measured latency is 16 clocks / 160 ns."),
    ],
    results=[("194.59 MHz", "clock after implementation, WNS +0.206 ns"),
             ("1,659 LUT", "3% of XC7Z020; FF 2,168 / BRAM 3 / DSP 2"),
             ("15.6 ms", "per frame at 1280×720"),
             ("196.7×", "speed-up over ARM software (Sobel)")],
    foot="Photo: host running OBS, receiving the board's HDMI output through a capture card.",
    band="Reproduce: sources, scripts and golden model in the repo, four steps rebuild it.   Verify: 0 differences across 8 presets, 16 / 21 clocks by dual timestamps.   Scope: HDMI 640×480@60; latency is PL pipeline only.",
)


def build(data, font):
    s = prs.slides.add_slide(blank)
    box(s, 0, 0, 13.333, 7.5, fill=WHITE)
    header(s, data["title"], data["subtitle"], data["tag"], data.get("tsize", 33))

    # 1 background / goal
    section(s, 0.55, 1.45, 3.80, "1", "背景与目标" if font == CN else "Background & Goal", font)
    bullets(s, 0.55, 1.92, 3.80, data["intro"], font, size=data.get("bsize", 10.8),
            step=data.get("bstep", 1.18))

    # 2 architecture (serpentine: top row left->right, bottom row right->left)
    section(s, 4.65, 1.45, 4.15, "2", "系统架构" if font == CN else "System Architecture", font)
    xs, w, h = [4.65, 6.05, 7.45], 1.15, 0.46
    y1, y2 = 1.92, 2.86
    for i, (label, sub) in enumerate(data["arch"]):
        cx = xs[i % 3]
        cy = y1 if i < 3 else y2
        node(s, cx, cy, w, h, label, font)
        text(s, cx, cy + h + 0.02, w, 0.16, sub, size=7.2, color=GREY, font=EN, align=PP_ALIGN.CENTER)
        if i < 2:
            arrow(s, cx + w + 0.02, cy + h / 2, cx + w + 0.21, cy + h / 2)
    arrow(s, xs[2] + w / 2, y1 + h + 0.16, xs[2] + w / 2, y2 - 0.02)
    for k in (2, 1):
        arrow(s, xs[k] - 0.02, y2 + h / 2, xs[k] - 0.21, y2 + h / 2)
    text(s, 4.65, 3.52, 4.15, 0.20, data["note"], size=8, color=ACCENT, font=font,
         align=PP_ALIGN.CENTER, bold=True)

    # 3 design
    section(s, 4.65, 3.76, 4.15, "3", "关键设计" if font == CN else "Key Design", font)
    cy = 4.18
    for head, body in data["design"]:
        text(s, 4.65, cy, 4.15, 0.20, head, size=9.3, color=INK, font=font, bold=True)
        text(s, 4.65, cy + 0.20, 4.15, 0.18, body, size=data.get("dsize", 8.0), color=GREY, font=font, spacing=1.05)
        cy += data.get("dstep", 0.52) if len(body) < 44 else data.get("dstep2", 0.70)

    # 4 results
    section(s, 9.05, 1.45, 3.75, "4", "结果" if font == CN else "Results", font)
    chip(s, 9.05, 1.90, 1.82, 0.74, data["results"][0][0], data["results"][0][1], font)
    chip(s, 10.98, 1.90, 1.82, 0.74, data["results"][1][0], data["results"][1][1], font)
    chip(s, 9.05, 2.72, 1.82, 0.74, data["results"][2][0], data["results"][2][1], font)
    chip(s, 10.98, 2.72, 1.82, 0.74, data["results"][3][0], data["results"][3][1], font)

    # 5 photo
    section(s, 9.05, 3.62, 3.75, "5", "演示现场" if font == CN else "Demo setup", font)
    s.shapes.add_picture(PHOTO, Inches(9.05), Inches(4.02), height=Inches(2.10))
    text(s, 9.05, 6.18, 3.75, 0.24, data["foot"], size=7.3, color=GREY, font=font, spacing=1.05)

    # bottom band
    box(s, 0.55, 6.62, 12.23, 0.62, fill=LIGHT)
    box(s, 0.55, 6.62, 0.055, 0.62, fill=ACCENT)
    text(s, 0.75, 6.70, 11.85, 0.46, data["band"], size=8.4, color=GREY, font=font, spacing=1.12)
    return s


build(CN_DATA, CN)
build(EN_DATA, EN)

os.makedirs(os.path.dirname(OUT), exist_ok=True)
prs.save(OUT)
print("saved", OUT, "slides", len(prs.slides))
