"""Generate the HDMI-path Jupyter panel.

Why a panel
    The DMA path already has one (board/enhance_dma/panel.ipynb) and it is what made that
    path demonstrable without a terminal. The HDMI path deserves the same: a judge - or a
    teammate - opens the notebook, clicks a preset, and sees the picture change on the
    capture card, with the measured pipeline latency printed underneath.

    It wraps hdmi_preset_only.py's sequence: writing a preset pulses the kernel reset (HLS
    samples the configuration in the pipeline prologue), so every switch also rebuilds the
    output path and refills the four frame buffers. Doing that by hand is easy to get wrong;
    behind a button it is one click.
"""

from __future__ import annotations

import json
import os

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(HERE, "board", "hdmi_stream_enhance", "notebooks",
                   "hdmi_panel.ipynb")


def md(text: str) -> dict:
    return {"cell_type": "markdown", "metadata": {},
            "source": text.splitlines(keepends=True)}


def code(text: str) -> dict:
    return {"cell_type": "code", "execution_count": None, "metadata": {},
            "outputs": [], "source": text.splitlines(keepends=True)}


CELLS = [
    md(
        "# HDMI 增强面板（640×480）\n"
        "\n"
        "**接线**：HDMI 采集卡插在板子的 **HDMI OUT**，USB 接电脑；电脑上打开 OBS 看采集源。\n"
        "不需要 HDMI 输入——这一版由 PS 送帧，内核在真实像素通路上处理。\n"
        "\n"
        "## 用法\n"
        "\n"
        "1. 从上到下依次运行单元格；\n"
        "2. 最后一个单元会出现一排按钮，点哪个就切到哪个预设；\n"
        "3. 每次切换后输出链路会自动重建（约 0.2 秒），之后画面稳定。\n"
        "\n"
        "> 说明：本板 HDMI 输出只能驱动 640×480（800×600/720p/1080p 下 VDMA 一帧都不消费，\n"
        "> 原厂位流同样如此）。切换预设时需要复位内核让 HLS 重新采样配置，\n"
        "> 所以每次点按钮会有一次约 0.2 秒的重连，这是已知代价。\n"
    ),
    code(
        "import time\n"
        "import numpy as np\n"
        "from pynq import Overlay\n"
        "from pynq.lib.video import VideoMode\n"
        "\n"
        "WIDTH, HEIGHT = 640, 480\n"
        "\n"
        "ol = Overlay(\"enhance_hdmi.bit\")\n"
        "video = ol.video\n"
        "out = video.hdmi_out\n"
        "\n"
        "hpd = None\n"
        "for name in ol.ip_dict:\n"
        "    if \"gpio_hdmiin\" in name.lower():\n"
        "        hpd = getattr(ol, name)\n"
        "if hpd is not None:\n"
        "    hpd.mmio.write(0x00, 0x1)      # 让 Windows 重新枚举 2 号屏\n"
        "\n"
        "cfg = None\n"
        "lat = None\n"
        "for name in ol.ip_dict:\n"
        "    if \"gpio_enh_cfg\" in name.lower():\n"
        "        cfg = getattr(ol, name)\n"
        "    if \"gpio_enh_lat\" in name.lower():\n"
        "        lat = getattr(ol, name)\n"
        "print(\"cfg:\", cfg is not None, \" latency:\", lat is not None)\n"
    ),
    md("## 预设与打包"),
    code(
        "# 59 位配置：word0 = clarity|knee|gain_lo|gain_hi，word1 = thresh|binarize|invert|mono|split_x\n"
        "PRESETS = {\n"
        "    \"pass\":     dict(clarity=16, knee=255, gain_lo=16, gain_hi=16),\n"
        "    \"clarity\":  dict(clarity=28, knee=255, gain_lo=16, gain_hi=16),\n"
        "    \"reading\":  dict(clarity=24, knee=48, gain_lo=88, gain_hi=14),\n"
        "    \"document\": dict(clarity=20, knee=192, gain_lo=64, gain_hi=12),\n"
        "    \"night\":    dict(clarity=30, knee=36, gain_lo=120, gain_hi=10),\n"
        "    \"invert\":   dict(clarity=24, knee=48, gain_lo=88, gain_hi=14, invert=1, mono=1),\n"
        "    \"binarize\": dict(clarity=16, knee=64, gain_lo=112, gain_hi=8,\n"
        "                      thresh=112, binarize=1, mono=1),\n"
        "    \"split\":    dict(clarity=28, knee=90, gain_lo=40, gain_hi=12, split_x=320),\n"
        "}\n"
        "\n"
        "\n"
        "def pack(p):\n"
        "    lo = ((p.get(\"clarity\", 16) & 0xFF)\n"
        "          | ((p.get(\"knee\", 255) & 0xFF) << 8)\n"
        "          | ((p.get(\"gain_lo\", 16) & 0xFF) << 16)\n"
        "          | ((p.get(\"gain_hi\", 16) & 0xFF) << 24))\n"
        "    hi = ((p.get(\"thresh\", 0) & 0xFF)\n"
        "          | ((p.get(\"binarize\", 0) & 1) << 8)\n"
        "          | ((p.get(\"invert\", 0) & 1) << 9)\n"
        "          | ((p.get(\"mono\", 0) & 1) << 10)\n"
        "          | ((p.get(\"split_x\", 0) & 0xFFFF) << 11))\n"
        "    return lo, hi\n"
        "\n"
        "print(len(PRESETS), \"presets\")\n"
    ),
    md("## 测试图与输出链路"),
    code(
        "def test_image():\n"
        "    img = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)\n"
        "    ramp = np.linspace(20, 235, HEIGHT, dtype=np.uint8).reshape(HEIGHT, 1)\n"
        "    img[:, :, 0] = ramp\n"
        "    img[:, :, 1] = ramp\n"
        "    img[:, :, 2] = ramp\n"
        "    top = HEIGHT // 2 - 60\n"
        "    img[top:top + 120, :, :] = 128\n"
        "    for row in range(top + 10, top + 110, 22):\n"
        "        left = 40\n"
        "        while left < WIDTH - 60:\n"
        "            run = int(30 + (left * 7) % 90)\n"
        "            img[row:row + 10, left:min(left + run, WIDTH - 40), :] = 25\n"
        "            left += run + 18\n"
        "    img[10:70, 10:130, 2] = 220\n"
        "    img[10:70, 140:260, 1] = 220\n"
        "    img[10:70, 270:390, 0] = 220\n"
        "    return img\n"
        "\n"
        "\n"
        "IMAGE = test_image()\n"
        "\n"
        "\n"
        "def apply_preset(name):\n"
        "    \"\"\"写配置即可生效。\n"
        "\n"
        "    内核从 BRAM 里每像素读配置（enhance_stream_cfg），所以一次寄存器写入下一个像素\n"
        "    就用上新参数：不复位、不中断像素流、不重建输出链路，画面不会黑一下。\n"
        "    实测证据见 hdmi_live_check.py：切档期间连续写帧 148 次、最大 14.4 ms、0 次卡顿。\n"
        "\n"
        "    旧版是端口配置的内核，需要在切档时复位内核才能让 prologue 重新采样，\n"
        "    而复位会打断像素流、让输出核欠载——那才是原来切换时闪一下的原因。\n"
        "    \"\"\"\n"
        "    lo, hi = pack(PRESETS[name])\n"
        "    cfg.mmio.write(0x00, lo)\n"
        "    cfg.mmio.write(0x08, hi)\n"
        "    time.sleep(0.001)\n"
        "    return read_latency()\n"
        "\n"
        "\n"
        "def read_latency():\n"
        "    a = lat.mmio.read(0x00)\n"
        "    b = lat.mmio.read(0x08)\n"
        "    if a == 0 and b == 0:\n"
        "        return None\n"
        "    return (b - a) & 0xFFFFFFFF\n"
        "\n"
        "print(\"ready\")\n"
    ),
    md("## 一键切换（点按钮）"),
    code(
        "import ipywidgets as widgets\n"
        "from IPython.display import display, clear_output\n"
        "\n"
        "status = widgets.Output()\n"
        "\n"
        "\n"
        "def make_button(name):\n"
        "    button = widgets.Button(description=name, layout=widgets.Layout(width=\"110px\"))\n"
        "\n"
        "    def on_click(_):\n"
        "        n = apply_preset(name)\n"
        "        with status:\n"
        "            clear_output(wait=True)\n"
        "            shown = \"未测到\" if n is None else f\"{n} 个像素时钟\"\n"
        "            print(f\"预设 {name} 已生效，流水线延迟 {shown}\")\n"
        "\n"
        "    button.on_click(on_click)\n"
        "    return button\n"
        "\n"
        "\n"
        "buttons = [make_button(n) for n in PRESETS]\n"
        "display(widgets.VBox([widgets.HBox(buttons[:4]),\n"
        "                      widgets.HBox(buttons[4:]), status]))\n"
    ),
    md(
        "## 显示你自己的图片\n"
        "\n"
        "点下面的按钮选一张图片（PNG / JPEG 都行），它会被缩放到 640×480 并显示在采集卡上。\n"
        "之后上面的预设按钮依然有效——**切换是瞬时的**，不需要重启输出链路，也不会黑屏。\n"
        "\n"
        "> 需要在板上安装 Pillow。若安装不了，就在电脑上用 `tools/make_frame.py` 转成\n"
        "> `frame.bin`，再 `scp` 到板上用 `--raw` 显示。\n"
        "\n"
        "> 非 4:3 的图片会**加黑边**（letterbox），不裁掉内容——这样画面上多出来的边框\n"
        "> 一看就知道不是处理效果。\n"
    ),
    code(
        "import io as _io\n"
        "import numpy as _np\n"
        "\n"
        "try:\n"
        "    from PIL import Image as _Image\n"
        "    _HAVE_PIL = True\n"
        "except Exception as _exc:                                    # noqa: BLE001\n"
        "    _HAVE_PIL = False\n"
        "    print(\"Pillow 不可用，请改用 tools/make_frame.py + --raw:\", _exc)\n"
        "\n"
        "\n"
        "def _fit(img):\n"
        "    img = img.convert(\"RGB\")\n"
        "    scale = min(WIDTH / img.width, HEIGHT / img.height)\n"
        "    size = (max(1, round(img.width * scale)), max(1, round(img.height * scale)))\n"
        "    resized = img.resize(size, _Image.LANCZOS)\n"
        "    canvas = _Image.new(\"RGB\", (WIDTH, HEIGHT), (0, 0, 0))\n"
        "    canvas.paste(resized, ((WIDTH - size[0]) // 2, (HEIGHT - size[1]) // 2))\n"
        "    return _np.asarray(canvas, dtype=_np.uint8)\n"
        "\n"
        "\n"
        "def show_picture(data):\n"
        "    if not _HAVE_PIL:\n"
        "        print(\"需要 Pillow\")\n"
        "        return\n"
        "    frame_image = _fit(_Image.open(_io.BytesIO(data)))\n"
        "    out.stop()\n"
        "    out.configure(VideoMode(WIDTH, HEIGHT, 24, 60))\n"
        "    out.start()\n"
        "    for _ in range(4):\n"
        "        buf = out.newframe()\n"
        "        buf[:] = frame_image\n"
        "        out.writeframe(buf)\n"
        "    print(f\"已显示，均值 {frame_image.mean():.1f}，延迟 {read_latency()} 拍\")\n"
        "\n"
        "\n"
        "upload = widgets.FileUpload(accept=\".png,.jpg,.jpeg,.bmp\", multiple=False,\n"
        "                            description=\"选择图片\")\n"
        "\n"
        "\n"
        "def _on_upload(change):\n"
        "    content = upload.value\n"
        "    if not content:\n"
        "        return\n"
        "    if isinstance(content, dict):                 # ipywidgets < 8\n"
        "        data = next(iter(content.values()))[\"content\"]\n"
        "    else:                                        # ipywidgets >= 8\n"
        "        data = content[0][\"content\"]\n"
        "    show_picture(bytes(data))\n"
        "\n"
        "\n"
        "upload.observe(_on_upload, names=\"value\")\n"
        "display(upload)\n"
    ),
    md("## 连续演示（自动循环，每档 15 秒）"),
    code(
        "import time\n"
        "\n"
        "ROUNDS = 1\n"
        "HOLD = 15\n"
        "\n"
        "order = [\"pass\", \"clarity\", \"reading\", \"document\",\n"
        "         \"night\", \"invert\", \"binarize\", \"split\"]\n"
        "\n"
        "for _ in range(ROUNDS):\n"
        "    for name in order:\n"
        "        n = apply_preset(name)\n"
        "        shown = \"未测到\" if n is None else f\"{n} 拍\"\n"
        "        print(f\"[{time.strftime('%H:%M:%S')}] {name:<9} 延迟 {shown}\")\n"
        "        time.sleep(HOLD)\n"
        "print(\"演示结束\")\n"
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
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(nb, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    print(f"wrote {OUT} ({len(CELLS)} cells)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
