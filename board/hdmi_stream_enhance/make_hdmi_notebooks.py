"""Generate the two HDMI notebooks (self-check + demo) from one place.

The same reason as make_panel_notebook.py: valid nbformat JSON, reviewable in the
repository, and regenerable when the code changes.

    python board/hdmi_stream_enhance/make_hdmi_notebooks.py
"""

from __future__ import annotations

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))


def md(text: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": text.splitlines(keepends=True)}


def code(text: str) -> dict:
    return {"cell_type": "code", "execution_count": None, "metadata": {},
            "outputs": [], "source": text.splitlines(keepends=True)}


SETUP = (
    "import time\n"
    "from pynq import Overlay\n"
    "import hdmi_live as hl\n"
    "\n"
    "ol = Overlay(\"enhance_hdmi.bit\")\n"
    "video = ol.video\n"
    "cfg = hl.find(ol, \"gpio_enh_cfg\")\n"
    "lat = hl.find(ol, \"gpio_enh_lat\")\n"
    "print(\"overlay loaded, IPS:\", len(ol.ip_dict))\n"
)

CHECK_CELLS = [
    md(
        "# 自检：overlay 能不能加载 + HDMI 输入有没有锁定\n"
        "\n"
        "**运行方式**：菜单 `Run` → `Run All Cells`，或者按 `Shift+Enter` 逐格运行。\n"
        "\n"
        "看两件事：\n"
        "1. `IPS:` 应该是一个大于 0 的数（说明位流加载成功）；\n"
        "2. `mode:` 应该是 `1280x720@60` 之类的值。\n"
        "\n"
        "**如果 `mode: None`**：线 A 没插好、笔记本没往外送信号，或者分辨率不是 PYNQ 能锁的模式。\n"
        "先把笔记本外接屏设成 1280×720，再重新运行一次这一格。\n"
    ),
    code(SETUP + "print(\"mode:\", video.hdmi_in.mode)\n"),
    md(
        "## 写一个预设并读回延迟\n"
        "\n"
        "`latency` 是内核流水线延迟（两个时间戳相减）。\n"
        "如果它是 `None`，说明上电后还没有像素流过——也就是输入还没锁定，先解决上一格。\n"
    ),
    code(
        "hl.write_preset(cfg, \"document\")\n"
        "print(\"preset document applied\")\n"
        "n = hl.read_latency(lat)\n"
        "print(\"latency:\", n, \"pixel clocks\" if n is not None else \"(not measured yet)\")\n"
        "if n is not None:\n"
        "    print(f\"         ~{n / 142.857 / 1000:.3f} us at 142.857 MHz\")\n"
    ),
]

DEMO_CELLS = [
    md(
        "# 演示：逐个切换预设（录视频用这一份）\n"
        "\n"
        "运行下面两格之后，**采集卡窗口里的画面会每 4 秒变一次**。\n"
        "改 `HOLD` 可以调整每个预设停留的秒数，改 `ORDER` 可以调整顺序。\n"
        "\n"
        "先运行第一格加载，再运行第二格开始循环；想停下就点工具栏的 ⏹。\n"
    ),
    code(SETUP + "print(\"mode:\", video.hdmi_in.mode)\n"),
    code(
        "HOLD = 4                     # 每个预设停留的秒数\n"
        "ORDER = [\"pass\", \"clarity\", \"document\", \"night\", \"invert\", \"binarize\", \"split\"]\n"
        "ROUNDS = 1                   # 想循环多轮就调大\n"
        "\n"
        "for r in range(ROUNDS):\n"
        "    for name in ORDER:\n"
        "        hl.write_preset(cfg, name)\n"
        "        n = hl.read_latency(lat)\n"
        "        stamp = time.strftime(\"%H:%M:%S\")\n"
        "        lat_txt = \"(no stamps yet)\" if n is None else f\"{n} pixel clocks (~{n / 142.857 / 1000:.3f} us)\"\n"
        "        print(f\"[{stamp}] {name:<9} latency {lat_txt}\")\n"
        "        time.sleep(HOLD)\n"
        "print(\"done\")\n"
    ),
    md(
        "## 录完之后\n"
        "\n"
        "把采集卡里的**原始画面**和**增强画面**各截一张图，连同上面的终端输出一起发我，\n"
        "我会把端到端证据补进设计报告和海报。\n"
    ),
]


def write(path: str, cells: list[dict]) -> None:
    nb = {
        "cells": cells,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python",
                           "name": "python3"},
            "language_info": {"name": "python", "version": "3.10"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(nb, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    print(f"wrote {path} ({len(cells)} cells)")


def main() -> int:
    write(os.path.join(HERE, "hdmi_check.ipynb"), CHECK_CELLS)
    write(os.path.join(HERE, "hdmi_demo.ipynb"), DEMO_CELLS)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
