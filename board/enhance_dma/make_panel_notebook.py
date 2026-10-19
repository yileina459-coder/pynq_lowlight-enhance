"""Generate board/enhance_dma/panel.ipynb (valid nbformat 4 JSON).

Writing the notebook from a script keeps the JSON well formed and makes the
notebook content reviewable in the repository, the same way make_poster.py
generates the poster.

    python board/enhance_dma/make_panel_notebook.py
"""

from __future__ import annotations

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "panel.ipynb")


def md(text: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": text.splitlines(keepends=True)}


def code(text: str) -> dict:
    return {"cell_type": "code", "execution_count": None, "metadata": {},
            "outputs": [], "source": text.splitlines(keepends=True)}


CELLS = [
    md(
        "# 低延迟视觉增强终端 — 交互控制面板\n"
        "\n"
        "这个面板直接驱动 `enhance_dma.bit`：**每一帧都真的经过 FPGA 内的 `enhance` 核**，\n"
        "图里显示的是 AXI-DMA 读回来的硬件输出，不是 numpy 模拟。\n"
        "\n"
        "点 **Run** 看当前预设，点 **Benchmark x20** 取 20 帧里最好的一次。\n"
        "右下角三行是这轮的全部证据：\n"
        "\n"
        "- **frame**：整帧往返时间（含 DMA 与 PS 开销）\n"
        "- **latency**：内核流水线填充延迟（内核前后各打一个时间戳相减）\n"
        "- **bit-exact**：与 numpy 黄金模型逐通道比对的结果，正常是 `0 / 2764800`\n"
    ),
    code(
        "from enhance_panel import EnhancePanel\n"
        "\n"
        "panel = EnhancePanel()          # 首次点击时才加载 overlay\n"
        "panel.show()\n"
    ),
    md(
        "## 一次跑完 8 个预设（录视频时用这一格）\n"
        "\n"
        "输出是一张表：每行一个预设的耗时、延迟与逐位比对结果。\n"
        "把上面面板里的预设逐个点一遍、下面这张表一并录进视频，就同时演示了\n"
        "**参数化**（寄存器实时改）与**正确性**（零容差比对）。\n"
    ),
    code(
        "rows = []\n"
        "for name in panel.presets:\n"
        "    r = panel.apply(name, frames=2)\n"
        "    rows.append((name, r['frame_ms'], r['latency_cycles'], r['mismatched']))\n"
        "\n"
        "print(f\"{'preset':<10}{'frame_ms':>10}{'latency':>10}{'mismatched':>12}\")\n"
        "for name, ms, lat, bad in rows:\n"
        "    print(f'{name:<10}{ms:>10.2f}{lat:>10}{bad:>12}')\n"
    ),
    md(
        "## 说明与边界\n"
        "\n"
        "- 这里走的是 **DMA 通路**，所以不需要显示器和采集卡；\n"
        "- **latency** 是内核流水线延迟（实测 16 个像素时钟 = 160 ns @100 MHz），\n"
        "  不是端到端延迟——端到端还要加上 HDMI 输入/输出链路，需要采集卡才能测；\n"
        "- `bit-exact` 用 `wrap` 边界（与 Sobel 参考图同一约定），因为硬件行缓冲里\n"
        "  保存的是上一帧的行；\n"
        "- 换个预设时，内核最多可能有一帧看到新旧参数混合，下一帧即正确。\n"
    ),
]


def main() -> int:
    nb = {
        "cells": CELLS,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python",
                           "name": "python3"},
            "language_info": {"name": "python", "version": "3.10"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(nb, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    print(f"wrote {OUT}  ({len(CELLS)} cells)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
