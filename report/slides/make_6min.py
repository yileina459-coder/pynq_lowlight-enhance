#!/usr/bin/env python3
"""Rebuild the 6-minute report deck from the 4-page draft, keeping its visual language.

Input : C:/Users/79171/Desktop/低延迟视觉增强终端_6分钟汇报.pptx  (4 pages, pages 01/02/06/07)
Output: C:/Users/79171/Desktop/低延迟视觉增强终端_6分钟汇报_优化版.pptx  (8 pages)

What changes
    * pages 03/04/05/08 are added (their numbers were missing from the draft)
    * page 06 (board verification) and 07 (performance) are rebuilt: the draft mixed the
      visual evidence with the DMA numbers, and its log axis stopped at 1000 while PS is
      3108.4 ms, so the PS bar ran past the end of the axis
    * cover: framed photo + platform line + three KPI chips + presenter line
    * page 02: figure enlarged, a closing line added under the right-hand column
    * "讲解约 50 秒" footer dropped; every page keeps a timing note instead

Design tokens are read off the original deck, so new pages match it:
    background F6F7F5 / cover 10252E / accent 168C87 / deep 0B6564
    ink 172B36 / body 52656B / rule D7DEDA / pill E2EBEF / mint DCEEE9
    orange E77845 / slate 4D7C96 / lime D5E96A (cover only) / 微软雅黑

Numbers come from report/design_report.md, docs/ and the board evidence in this repo;
the narrative follows the desktop report 低延迟视觉增强终端_作品报告.docx.
"""

from __future__ import annotations

import copy
import os
import re
import zipfile

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, MSO_AUTO_SIZE, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Inches as In, Pt

SRC = r"C:\Users\79171\Desktop\低延迟视觉增强终端_6分钟汇报.pptx"
OUT = r"C:\Users\79171\Desktop\低延迟视觉增强终端_6分钟汇报_优化版.pptx"
REPO = r"C:\Users\79171\Desktop\FPGA"
PRESETS_2X2 = os.path.join(REPO, "board", "hdmi_stream_enhance", "evidence", "hdmi_presets_2x2.png")

FONT = "微软雅黑"

BG = RGBColor(0xF6, 0xF7, 0xF5)
COVER_BG = RGBColor(0x10, 0x25, 0x2E)
TEAL = RGBColor(0x16, 0x8C, 0x87)
DEEP = RGBColor(0x0B, 0x65, 0x64)
INK = RGBColor(0x17, 0x2B, 0x36)
BODY = RGBColor(0x52, 0x65, 0x6B)
RULE = RGBColor(0xD7, 0xDE, 0xDA)
PILL = RGBColor(0xE2, 0xEB, 0xEF)
MINT = RGBColor(0xDC, 0xEE, 0xE9)
ORANGE = RGBColor(0xE7, 0x78, 0x45)
SLATE = RGBColor(0x4D, 0x7C, 0x96)
GREY = RGBColor(0x95, 0xA7, 0xA8)
LIME = RGBColor(0xD5, 0xE9, 0x6A)
PALE = RGBColor(0xD2, 0xDF, 0xDE)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)

W, H = 13.3333, 7.5
M = 0.67
CW = 12.0


# --------------------------------------------------------------------------- text helpers


def _ea(run):
    rPr = run._r.get_or_add_rPr()
    ea = rPr.find(qn("a:ea"))
    if ea is None:
        ea = rPr.makeelement(qn("a:ea"), {})
        latin = rPr.find(qn("a:latin"))
        (latin.addnext(ea) if latin is not None else rPr.append(ea))
    ea.set("typeface", FONT)


def write(tf, text, size, bold=False, color=INK, spacing=1.0, align=PP_ALIGN.LEFT, before=0,
          after=0, first=False):
    p = tf.paragraphs[0] if first else tf.add_paragraph()
    p.line_spacing = spacing
    p.alignment = align
    if before:
        p.space_before = Pt(before)
    if after:
        p.space_after = Pt(after)
    r = p.add_run()
    r.text = text
    r.font.size = Pt(size)
    r.font.bold = bold
    r.font.color.rgb = color
    r.font.name = FONT
    _ea(r)
    return p


def rich(tf, items, first=False, spacing=1.2, align=PP_ALIGN.LEFT, before=0):
    """One paragraph made of several differently styled runs."""
    p = tf.paragraphs[0] if first else tf.add_paragraph()
    p.line_spacing = spacing
    p.alignment = align
    if before:
        p.space_before = Pt(before)
    for text, size, bold, color in items:
        r = p.add_run()
        r.text = text
        r.font.size = Pt(size)
        r.font.bold = bold
        r.font.color.rgb = color
        r.font.name = FONT
        _ea(r)
    return p


def tb(slide, x, y, w, h, anchor=MSO_ANCHOR.TOP, align=PP_ALIGN.LEFT, margins=(0, 0, 0, 0)):
    box = slide.shapes.add_textbox(In(x), In(y), In(w), In(h))
    tf = box.text_frame
    tf.word_wrap = True
    tf.auto_size = MSO_AUTO_SIZE.NONE
    tf.vertical_anchor = anchor
    tf.margin_left, tf.margin_top, tf.margin_right, tf.margin_bottom = (In(v) for v in margins)
    tf.paragraphs[0].alignment = align
    return tf


def shape_text(shape, anchor=MSO_ANCHOR.MIDDLE, margins=(0.08, 0.03, 0.08, 0.03)):
    tf = shape.text_frame
    tf.word_wrap = True
    tf.auto_size = MSO_AUTO_SIZE.NONE
    tf.vertical_anchor = anchor
    tf.margin_left, tf.margin_top, tf.margin_right, tf.margin_bottom = (In(v) for v in margins)
    return tf


def rect(slide, x, y, w, h, fill=None, line=None, lw=0.9, radius=None,
         shape=MSO_SHAPE.ROUNDED_RECTANGLE):
    s = slide.shapes.add_shape(shape, In(x), In(y), In(w), In(h))
    if radius is not None and shape == MSO_SHAPE.ROUNDED_RECTANGLE:
        s.adjustments[0] = radius
    if fill is None:
        s.fill.background()
    else:
        s.fill.solid()
        s.fill.fore_color.rgb = fill
    if line is None:
        s.line.fill.background()
    else:
        s.line.color.rgb = line
        s.line.width = Pt(lw)
    s.shadow.inherit = False
    return s


def arrow(slide, x, y, w=0.16, h=0.16, color=GREY):
    s = rect(slide, x, y, w, h, fill=color, shape=MSO_SHAPE.RIGHT_ARROW)
    return s


# --------------------------------------------------------------------------- page scaffolding


def new_content(prs, page, kicker, title):
    s = prs.slides.add_slide(prs.slide_layouts[5])
    s.background.fill.solid()
    s.background.fill.fore_color.rgb = BG

    rect(s, 0, 0, 0.12, H, fill=TEAL, shape=MSO_SHAPE.RECTANGLE)
    write(tb(s, M, 0.38, 6.25, 0.23), kicker, 9.75, True, DEEP, first=True)
    write(tb(s, M, 0.70, 11.9, 0.66), title, 27, True, INK, first=True)
    rect(s, M, 1.49, CW, 0.012, fill=RULE, shape=MSO_SHAPE.RECTANGLE)
    write(tb(s, 10.6, 7.06, 2.0, 0.21, align=PP_ALIGN.RIGHT), f"{page:02d} / 08",
          9.75, False, BODY, first=True, align=PP_ALIGN.RIGHT)
    return s


def notes(slide, text):
    slide.notes_slide.notes_text_frame.text = text


# --------------------------------------------------------------------------- slide builders


def build_solution(prs):
    """03 系统方案."""
    s = new_content(prs, 3, "系统方案", "两条通路，同一份算法源码")

    write(tb(s, M, 1.74, 9.5, 0.3), "演示通路（HDMI）：增强核位于真实像素流上",
          15, True, INK, first=True)

    blocks = [("PS / Jupyter", "送帧 · 写配置", False),
              ("DDR + VDMA", "按显示速率供帧", False),
              ("SOF 对齐", "TUSER 帧起始", False),
              ("enhance 核", "像素流内逐拍增强", True),
              ("vid_out", "重建视频时序", False),
              ("HDMI 640×480", "采集卡回采", False)]
    bw, gap = 1.8167, 0.22
    x = M
    for i, (title, sub, hot) in enumerate(blocks):
        b = rect(s, x, 2.10, bw, 0.86, fill=TEAL if hot else PILL, radius=0.10)
        tf = shape_text(b)
        write(tf, title, 12.5, True, WHITE if hot else INK, first=True, align=PP_ALIGN.CENTER)
        write(tf, sub, 9, False, RGBColor(0xD6, 0xEF, 0xEA) if hot else BODY,
              before=2, align=PP_ALIGN.CENTER)
        if i < len(blocks) - 1:
            arrow(s, x + bw + 0.03, 2.45, 0.16, 0.16)
        x += bw + gap

    write(tb(s, M, 3.36, 9.8, 0.3), "数字验证通路（AXI-DMA）：同一份源码，可回读、可逐位比对",
          15, True, INK, first=True)

    band = rect(s, M, 3.72, CW, 0.72, fill=PILL, radius=0.10)
    tf = shape_text(band, margins=(0.26, 0.04, 0.26, 0.04))
    tf.clear()
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.LEFT
    for text, size, bold, color in [("DDR ", 13, False, INK), ("→", 13, False, GREY),
                                    (" AXI-DMA MM2S ", 13, True, INK), ("→", 13, False, GREY),
                                    (" enhance（有界核）", 13, True, DEEP), (" →", 13, False, GREY),
                                    (" AXI-DMA S2MM ", 13, True, INK), ("→", 13, False, GREY),
                                    (" DDR 回读 ", 13, True, INK), ("→", 13, False, GREY),
                                    (" NumPy 黄金模型逐通道比对", 13, False, INK)]:
        r = p.add_run()
        r.text = text
        r.font.size = Pt(size)
        r.font.bold = bold
        r.font.color.rgb = color
        r.font.name = FONT
        _ea(r)

    points = [("零帧缓存", "增强链在像素流内完成，运算不落 DDR；PS 只送帧与写配置，不参与像素运算。"),
              ("一份源码 · 两条通路", "DMA 版 ap_ctrl_hs 可回读；HDMI 版 ap_ctrl_none 自由运行。两者共用 enhance.cpp。"),
              ("帧源为什么是 VDMA", "实测 HDMI 输出只支持 640×480，而 HDMI 输入不支持该模式：直通无解，改由 VDMA 供帧。")]
    x = M
    for title, body in points:
        rect(s, x, 4.86, 0.05, 0.34, fill=TEAL, shape=MSO_SHAPE.RECTANGLE)
        write(tb(s, x + 0.18, 4.84, 3.5, 0.3), title, 14.5, True, DEEP, first=True)
        write(tb(s, x + 0.18, 5.22, 3.55, 1.10), body, 11.5, False, BODY, first=True, spacing=1.3)
        x += 4.04

    write(tb(s, M, 6.55, CW, 0.3), "位流 enhance_hdmi.bit · WNS +0.206 ns @142.857 MHz · 失败端点 0",
          10, False, BODY, first=True)

    notes(s, "【1:10–1:55 系统方案 45 秒】\n"
             "上面这条是演示通路：PS 把帧写进 DDR，VDMA 按显示速率供帧，SOF 生成器把帧起始锚定好，"
             "像素流穿过增强核，再由 vid_out 和 rgb2dvi 送出 HDMI。增强核就在真实像素通路上。\n"
             "下面这条是数字验证通路：同一份 enhance.cpp 换成有界核，用 AXI-DMA 整帧搬进搬出，"
             "回读后跟 NumPy 黄金模型逐通道比，不需要显示器。\n"
             "为什么帧源是 VDMA 而不是 HDMI 输入？这块板的 HDMI 输出只支持 640×480，输入 IP 又不支持 640×480，"
             "原厂位流也是同样结果，所以直通无解——这是板卡上限，不是没调通。")
    return s


def build_kernel(prs):
    """04 核心算子."""
    s = new_content(prs, 4, "核心算子", "四段流水线，59 位参数逐像素生效")

    write(tb(s, M, 1.74, 10.0, 0.3), "全部整数定点，无浮点；每拍处理一个像素（II = 1）",
          15, True, INK, first=True)

    stages = [("01", "局部对比", "clarity", "先算 3×3 局部均值，再放大细节"),
              ("02", "两段色调曲线", "knee · gain_lo · gain_hi", "拐点以下、以上分别给不同增益"),
              ("03", "二值 · 反色 · 单色", "thresh · invert · mono", "硬阈值切分，可反色、去色"),
              ("04", "分屏", "split_x", "同一帧内左原始、右处理")]
    cw, gap = 2.82, 0.24
    x = M
    for num, title, params, desc in stages:
        card = rect(s, x, 2.08, cw, 1.66, fill=WHITE, line=RULE, lw=0.75, radius=0.06)
        rect(s, x, 2.08, cw, 0.05, fill=TEAL, shape=MSO_SHAPE.RECTANGLE)
        tf = shape_text(card, anchor=MSO_ANCHOR.TOP, margins=(0.18, 0.16, 0.16, 0.08))
        write(tf, num, 9.5, True, SLATE, first=True)
        write(tf, title, 15, True, INK, before=3)
        write(tf, params, 9.75, False, DEEP, before=4)
        write(tf, desc, 10, False, BODY, before=6, spacing=1.2)
        x += cw + gap

    chips = [("II = 1", "每拍一像素"), ("3 BRAM · 2 DSP", "1659 LUT，约 3%"),
             ("194.59 MHz", "7 ns 约束估计"), ("59 bit", "运行期参数"), ("10 档预设", "运行期一键切换")]
    cw2 = 2.24
    x = M
    for big, small in chips:
        c = rect(s, x, 3.96, cw2, 0.94, fill=MINT, radius=0.10)
        tf = shape_text(c)
        write(tf, big, 15, True, DEEP, first=True, align=PP_ALIGN.CENTER)
        write(tf, small, 9, False, BODY, before=3, align=PP_ALIGN.CENTER)
        x += cw2 + 0.20

    band = rect(s, M, 5.18, CW, 1.12, fill=None, line=RULE, lw=0.75, radius=0.06)
    rect(s, M, 5.18, 0.06, 1.12, fill=ORANGE, shape=MSO_SHAPE.RECTANGLE)
    tf = shape_text(band, margins=(0.28, 0.12, 0.26, 0.10))
    write(tf, "配置驻留双口 BRAM：59 位参数逐像素读取，规避 HLS prologue 锁存 —— 换预设只需一次寄存器写，视频流不中断。",
          12, True, INK, first=True, spacing=1.2)
    write(tf, "XPM 真双口替代触发器推断：WNS −1.393 → +0.289 ns（交付位流 +0.206），失败端点 59 → 0。",
          11, False, BODY, before=6, spacing=1.2)

    write(tb(s, M, 6.55, CW, 0.3),
          "边界规则写进头文件、C++ 测试台与 NumPy 参考：水平复制边缘、垂直沿用上一行 —— 所以可以要求 0 容差。",
          10, False, BODY, first=True)

    notes(s, "【1:55–2:35 核心算子 40 秒】\n"
             "增强核只有一条流水线，四段：局部对比、两段色调曲线、二值/反色/单色、分屏。"
             "参数一共 59 位，由 PS 在运行期写进来。\n"
             "实现上全整数定点，每拍一个像素，综合下来 II 等于 1，估计最高频率 194.59 兆；"
             "资源 3 块 BRAM、2 个 DSP、1659 个 LUT，大约 3%。\n"
             "这里有个关键设计：参数放在双口 BRAM 里按像素读。因为 HLS 会把循环不变量锁进流水线启动阶段，"
             "参数放寄存器的话，换预设必须复位内核、画面会断。搬进 BRAM 之后换预设只是一次寄存器写。")
    return s


def build_latency(prs):
    """05 延迟测量."""
    s = new_content(prs, 5, "延迟测量", "21 个像素时钟：延迟是固定的，不随内容变化")

    write(tb(s, M, 1.74, 10.5, 0.3), "方法：内核前后各打一次时间戳，同一时钟、同一复位，两个数相减",
          15, True, INK, first=True)

    # measurement diagram
    blocks = [(0.67, 1.30, "轴时间戳 A", "首个像素进入", False),
              (2.45, 2.60, "enhance 核", "21 级流水", True),
              (5.53, 1.30, "轴时间戳 B", "首个像素输出", False)]
    for x, w, title, sub, hot in blocks:
        b = rect(s, x, 2.32, w, 0.92, fill=TEAL if hot else PILL, radius=0.10)
        tf = shape_text(b)
        write(tf, title, 13, True, WHITE if hot else INK, first=True, align=PP_ALIGN.CENTER)
        write(tf, sub, 9.5, False, RGBColor(0xD6, 0xEF, 0xEA) if hot else BODY,
              before=2, align=PP_ALIGN.CENTER)
    arrow(s, 2.02, 2.70, 0.34, 0.16, TEAL)
    arrow(s, 5.10, 2.70, 0.34, 0.16, TEAL)

    # dimension line under the three blocks
    dim = RGBColor(0xBF, 0xCF, 0xCB)
    rect(s, 1.32, 3.50, 5.51, 0.008, fill=dim, shape=MSO_SHAPE.RECTANGLE)
    rect(s, 1.32, 3.44, 0.008, 0.12, fill=dim, shape=MSO_SHAPE.RECTANGLE)
    rect(s, 6.82, 3.44, 0.008, 0.12, fill=dim, shape=MSO_SHAPE.RECTANGLE)
    write(tb(s, 1.32, 3.62, 5.51, 0.28, align=PP_ALIGN.CENTER), "两时间戳之差 = 流水线深度",
          9.5, False, BODY, first=True, align=PP_ALIGN.CENTER)

    # right: the numbers
    number = tb(s, 8.55, 1.94, 1.30, 1.25)
    number.word_wrap = False
    rich(number, [("21", 74, True, TEAL)], first=True)
    write(tb(s, 9.70, 2.88, 0.55, 0.45), "拍", 20, True, TEAL, first=True)
    write(tb(s, 8.60, 3.42, 3.9, 0.5), "≈ 0.15 µs", 24, True, DEEP, first=True)
    write(tb(s, 8.60, 3.92, 3.9, 0.3), "142.857 MHz 像素时钟域", 11, False, BODY, first=True)
    write(tb(s, 8.60, 4.30, 3.9, 0.6), "约为一帧（16.7 ms）的 1/110,000，\n也远小于一行（31.8 µs）。",
          11, False, BODY, first=True, spacing=1.3)

    facts = [("HLS 报告 Depth = 21", "综合与板上读数一致"),
             ("DMA 通路 16 拍", "160 ns @100 MHz"),
             ("预设切换全程 21 拍", "不随内容或预设变化")]
    x = M
    for big, small in facts:
        c = rect(s, x, 5.10, 3.82, 0.94, fill=MINT, radius=0.10)
        tf = shape_text(c)
        write(tf, big, 13, True, DEEP, first=True)
        write(tf, small, 9.5, False, BODY, before=3)
        x += 4.04

    write(tb(s, M, 6.45, CW, 0.3),
          "口径：只测 PL 内部的流水线延迟；端到端（含采集与显示）受板卡 HDMI 输出上限限制，未实测。",
          10, False, BODY, first=True)

    notes(s, "【2:35–3:15 延迟测量 40 秒】\n"
             "延迟怎么证明？在内核前后各放一个时间戳模块，同一个时钟、同一个复位，"
             "第一个像素进和出各记一次，两个数相减就是流水线深度。\n"
             "结果是 21 拍，HLS 报告的 Depth 也是 21，两边对得上。按 142.857 兆算，大约是 0.15 微秒。\n"
             "换个说法：一帧是 16.7 毫秒，这个延迟大约是一帧的十一万分之一；640×480 的一行是 31.8 微秒，"
             "所以延迟远小于一行，而且不随画面内容变化。\n"
             "口径要讲清楚：这只测 PL 内部；端到端含采集卡和显示，受这块板 HDMI 只到 640×480 的限制，没有实测。")
    return s


def build_board(prs):
    """06 板上验证（重建）. """
    s = new_content(prs, 6, "板上验证", "画面看效果，回读看正确性")

    s.shapes.add_picture(PRESETS_2X2, In(0.67), In(1.76), width=In(6.10))
    write(tb(s, M, 6.42, 6.1, 0.3), "同一测试图、四种预设的 HDMI 采集卡实拍（640×480）",
          10, False, BODY, first=True)
    write(tb(s, M, 1.56, 6.1, 0.25), "视觉证据 · HDMI 通路", 9.5, True, SLATE, first=True)

    rect(s, 7.02, 1.76, 0.012, 4.55, fill=RULE, shape=MSO_SHAPE.RECTANGLE)

    write(tb(s, 7.35, 1.76, 5.0, 0.3), "数值证据 · AXI-DMA 通路", 9.5, True, SLATE, first=True)
    write(tb(s, 7.35, 2.02, 1.6, 1.25), "0", 78, True, TEAL, first=True)
    write(tb(s, 8.05, 2.62, 4.3, 0.4), "个通道差异", 18, True, INK, first=True)
    write(tb(s, 7.38, 3.34, 4.95, 0.9),
          "8 档（验证参数表）× 2,764,800 个 RGB 通道，全部与 NumPy 黄金模型逐位一致。",
          12.5, False, BODY, first=True, spacing=1.35)

    mini = [("8 档验证表", "逐一回读比对"), ("15.6 ms/帧", "1280×720 整帧")]
    x = 7.38
    for big, small in mini:
        c = rect(s, x, 4.30, 2.35, 0.86, fill=MINT, radius=0.10)
        tf = shape_text(c)
        write(tf, big, 13.5, True, DEEP, first=True)
        write(tf, small, 9.5, False, BODY, before=3)
        x += 2.55

    note = rect(s, 7.38, 5.42, 4.95, 0.86, fill=None, line=RULE, lw=0.75, radius=0.06)
    tf = shape_text(note, margins=(0.18, 0.08, 0.16, 0.08))
    write(tf, "画面只能证明图像确实经过内核；逐位正确性由 DMA 回读证明。两件事分开陈述。",
          10.5, False, BODY, first=True, spacing=1.25)

    notes(s, "【3:15–4:10 板上验证 55 秒】\n"
             "这一页把两类证据分开。左边是 HDMI 通路上采集卡抓的四张画面，同一张测试图、四种预设："
             "能看出色调、阈值、分屏确实在逐帧起作用。\n"
             "但画面只能证明图像真的经过了内核，不能证明逐位正确——因为 HDMI 通路的帧回读不到。\n"
             "所以正确性由右边这条 DMA 通路给出：每档回读一张 1280×720 的 RGB 图，2,764,800 个通道，"
             "八档（验证参数表）全部跟 NumPy 模型逐位一致，差异 0，单帧 15.6 毫秒。")
    return s


def build_perf(prs):
    """07 量化结果（重建，对数轴补到 10000）."""
    s = new_content(prs, 7, "量化结果", "性能：整帧 DMA 释放了硬件吞吐")

    write(tb(s, M, 1.74, 9.0, 0.3), "1280×720 Sobel · 同板、同图、同算法 · 输出逐位一致",
          14.25, False, BODY, first=True)

    x0, decade = 3.05, 1.55
    axis_end = x0 + 4 * decade          # 1 .. 10000
    rows = [("PS · ARM + NumPy", 3108.4, "3108.4 ms", SLATE),
            ("PL · 逐行 DMA", 659.1, "659.1 ms", RGBColor(0x95, 0xA7, 0xA8)),
            ("PL · 整帧 DMA", 15.8, "15.8 ms", ORANGE)]
    import math
    for i, (label, ms, value, color) in enumerate(rows):
        y = 2.32 + i * 1.02
        write(tb(s, M, y + 0.06, 2.25, 0.32, align=PP_ALIGN.RIGHT), label, 14, True, INK,
              first=True, align=PP_ALIGN.RIGHT)
        w = max(0.045, math.log10(ms) * decade)
        rect(s, x0, y, w, 0.44, fill=color, radius=0.02,
             shape=MSO_SHAPE.ROUNDED_RECTANGLE if w > 0.4 else MSO_SHAPE.RECTANGLE)
        write(tb(s, x0 + w + 0.14, y + 0.05, 1.5, 0.34),
              value, 14, True, color if i == 2 else INK, first=True)

    # axis
    axis_y = 5.28
    rect(s, x0, axis_y, axis_end - x0, 0.012, fill=RULE, shape=MSO_SHAPE.RECTANGLE)
    for k in range(5):
        tx = x0 + k * decade
        rect(s, tx, axis_y, 0.01, 0.10, fill=RGBColor(0xB9, 0xC6, 0xC2), shape=MSO_SHAPE.RECTANGLE)
        write(tb(s, tx - 0.35, axis_y + 0.14, 0.7, 0.25, align=PP_ALIGN.CENTER),
              str(10 ** k), 10.5, False, BODY, first=True, align=PP_ALIGN.CENTER)
    write(tb(s, x0, axis_y + 0.46, 4.2, 0.25), "每帧耗时（对数刻度，ms）", 11, False, BODY, first=True)

    # right panel
    rect(s, 9.98, 1.76, 0.012, 4.20, fill=RULE, shape=MSO_SHAPE.RECTANGLE)
    write(tb(s, 10.28, 1.88, 2.6, 0.7), "196.7×", 34, True, DEEP, first=True)
    write(tb(s, 10.30, 2.62, 2.5, 0.6), "PL 整帧 DMA\n相对 PS 提升", 12, False, INK, first=True,
          spacing=1.2)
    pill = rect(s, 10.26, 3.30, 2.10, 0.50, fill=MINT, radius=0.18)
    write(shape_text(pill), "输出逐位一致", 12, True, DEEP, first=True, align=PP_ALIGN.CENTER)
    write(tb(s, 10.30, 4.02, 2.5, 1.2), "15.8 ms/帧", 14, True, INK, first=True)
    write(tb(s, 10.30, 4.34, 2.5, 1.2), "63.45 fps", 14, True, INK, first=True)
    write(tb(s, 10.30, 4.66, 2.5, 1.2), "58.47 Mpixel/s", 14, True, INK, first=True)

    write(tb(s, M, 6.42, CW, 0.5),
          "对数刻度。逐行的 659 ms 主要来自每帧 720 次内核启动与 1440 次 DMA 的软件开销，不是算子时间。",
          10, False, BODY, first=True)

    notes(s, "【4:10–5:15 量化结果 65 秒】\n"
             "这组 Sobel 数据在同一块 PYNQ-Z2、同一张 1280×720 图上测。纵轴是对数刻度，因为三条差了两个数量级。\n"
             "纯软件 ARM 加 NumPy 每帧 3108 毫秒；PL 逐行 DMA 是 659 毫秒；改成整帧 DMA 之后 15.8 毫秒，提升 196.7 倍，"
             "63.45 帧每秒。\n"
             "中间那条要解释一下：659 毫秒里绝大部分不是算子时间，而是每帧 720 次内核启动、1440 次 DMA 传输和轮询的软件开销；"
             "整帧传输把启动次数压到一次，才接近 PL 的真实吞吐。\n"
             "三种实现的输出逐位一致，所以这个提升不是用精度换的。")
    return s


def build_conclusion(prs):
    """08 结论."""
    s = new_content(prs, 8, "结论", "延迟、可信、可复现")

    cards = [("21 个时钟", "零帧缓存流水线", "延迟由流水线级数决定，与画面内容、帧率无关；换预设不中断视频流。"),
             ("0 / 2,764,800", "可信的证据链", "8 档（验证表）逐位一致；196.7× 不以精度换速度，输出逐位相同。"),
             ("2 条命令", "可复现", "位流、报告与证据全部脚本化；5 个 PYNQ Skill 可迁移到别的板卡与题目。")]
    cw, gap = 3.82, 0.215
    x = M
    for big, title, body in cards:
        card = rect(s, x, 1.80, cw, 2.18, fill=WHITE, line=RULE, lw=0.75, radius=0.06)
        rect(s, x, 1.80, cw, 0.05, fill=TEAL, shape=MSO_SHAPE.RECTANGLE)
        tf = shape_text(card, anchor=MSO_ANCHOR.TOP, margins=(0.22, 0.18, 0.20, 0.10))
        write(tf, big, 25, True, TEAL, first=True)
        write(tf, title, 14, True, INK, before=6)
        write(tf, body, 10.5, False, BODY, before=8, spacing=1.3)
        x += cw + gap

    band = rect(s, M, 4.24, CW, 0.82, fill=None, line=RULE, lw=0.75, radius=0.06)
    tf = shape_text(band, margins=(0.26, 0.08, 0.24, 0.08))
    rich(tf, [("已知限制  ", 11, True, ORANGE),
              ("HDMI 只能 640×480（板卡上限）· 端到端与功耗未实测 · "
               "Sobel / 高斯 / 锐化三算子未并行进同一 overlay", 11, False, BODY)],
         first=True, spacing=1.2)

    write(tb(s, 0.70, 5.28, 7.0, 0.6), "谢谢，欢迎提问", 26, True, INK, first=True)
    write(tb(s, 0.72, 5.98, 8.4, 0.3),
          "交付：enhance_hdmi.bit · 源码与构建脚本 · 设计报告 · 5 个 PYNQ Skill",
          10.5, False, BODY, first=True)

    notes(s, "【5:15–5:50 结论 35 秒】\n"
             "三句话收尾：第一，延迟是固定的 21 个时钟，换预设也不中断；"
             "第二，正确性有 0 容差的逐位比对，性能提升没有牺牲精度；"
             "第三，整套东西是脚本化的，换一块板子也能重建。\n"
             "限制也如实说：这块板 HDMI 只能 640×480，端到端和功耗没测，三个算子还没进同一个 overlay。\n"
             "谢谢各位老师，欢迎提问。")
    return s


# --------------------------------------------------------------------------- existing-page edits


def edit_cover(prs):
    s = prs.slides[0]
    pic = next(sh for sh in s.shapes if sh.shape_type == 13)
    pic.width = In(5.86)
    pic.height = In(5.86 * 473 / 1247)
    pic.left = In(6.62)
    pic.top = In(2.42)
    pic.line.color.rgb = RGBColor(0x47, 0x61, 0x6A)
    pic.line.width = Pt(1.25)

    write(tb(s, 6.62, 2.16, 5.8, 0.24), "实物与演示现场", 9.5, True, LIME, first=True)

    # platform line
    line = next(sh for sh in s.shapes
                if sh.has_text_frame and sh.text_frame.text.strip() == "PYNQ-Z2")
    line.width = In(6.1)
    tf = line.text_frame
    tf.word_wrap = True
    tf.paragraphs[0].runs[0].text = "PYNQ-Z2（XC7Z020）· Vivado / Vitis HLS 2026.1"
    tf.paragraphs[0].runs[0].font.size = Pt(11.5)

    write(tb(s, 0.81, 5.36, 5.5, 0.28), "2026 全国大学生嵌入式芯片与系统设计竞赛 · AMD 自主选题（初级组）",
          9.5, False, RGBColor(0x8F, 0xA3, 0xA7), first=True)
    write(tb(s, 0.81, 5.70, 5.5, 0.28), "汇报人：＿＿＿＿＿＿　　2026 年 10 月",
          10, False, RGBColor(0x8F, 0xA3, 0xA7), first=True)

    chips = [("21 拍", "流水线延迟"), ("0 通道", "逐位比对差异"), ("196.7×", "相对 ARM 提升")]
    x = 6.62
    for big, small in chips:
        rect(s, x, 5.42, 1.86, 0.02, fill=LIME, shape=MSO_SHAPE.RECTANGLE)
        write(tb(s, x, 5.54, 1.86, 0.4), big, 20, True, LIME, first=True)
        write(tb(s, x, 5.98, 1.86, 0.3), small, 9.5, False, RGBColor(0x9F, 0xB0, 0xB4), first=True)
        x += 1.98


def edit_problem(prs):
    s = prs.slides[1]
    pic = next(sh for sh in s.shapes if sh.shape_type == 13)
    pic.width = In(5.60)
    pic.height = In(5.60 * 483 / 1178)
    pic.left = In(7.05)
    pic.top = In(2.30)

    rect(s, 7.05, 6.34, 5.55, 0.012, fill=RULE, shape=MSO_SHAPE.RECTANGLE)
    write(tb(s, 7.05, 6.44, 5.55, 0.45),
          "延迟由流水线级数决定，与画面内容、帧率无关。", 11, False, BODY, first=True)

    for sh in s.shapes:
        if not sh.has_text_frame:
            continue
        text = sh.text_frame.text.strip()
        if text == "暗光书页实拍对比":
            sh.top = In(4.74)
        elif text.startswith("提亮并增强局部对比"):
            sh.top = In(5.14)
        elif re.fullmatch(r"\d\d\s*/\s*08", text):
            sh.left, sh.top, sh.width, sh.height = In(10.6), In(7.06), In(2.0), In(0.21)
            para = sh.text_frame.paragraphs[0]
            para.alignment = PP_ALIGN.RIGHT
            if para.runs:
                para.runs[0].text = "02 / 08"


def drop_slide(prs, index):
    sld_id = prs.slides._sldIdLst[index]
    prs.part.drop_rel(sld_id.rId)
    prs.slides._sldIdLst.remove(sld_id)


def normalise_slide_type(path):
    tmp = path + ".tmp"
    with zipfile.ZipFile(path) as zin, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "ppt/presentation.xml":
                text = data.decode("utf-8")
                text = re.sub(r'<p:sldSz([^>]*?)type="[^"]*"', r'<p:sldSz\1type="screen16x9"', text)
                data = text.encode("utf-8")
            zout.writestr(item, data)
    os.replace(tmp, path)


def main() -> int:
    prs = Presentation(SRC)

    edit_cover(prs)
    edit_problem(prs)

    # draft pages 3 and 4 are rebuilt below; drop them first
    drop_slide(prs, 3)
    drop_slide(prs, 2)

    build_solution(prs)
    build_kernel(prs)
    build_latency(prs)
    build_board(prs)
    build_perf(prs)
    build_conclusion(prs)

    prs.save(OUT)
    normalise_slide_type(OUT)
    print(f"wrote {OUT} ({len(prs.slides)} slides)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
