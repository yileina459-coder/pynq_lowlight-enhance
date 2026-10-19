# enhance_hdmi — 真机 HDMI 增强通路

```
HDMI 源（笔记本） ──线 A──► PYNQ HDMI IN
                              │  dvi2rgb → pixel_pack
                              │  → stamp_in → enhance → stamp_out
                              │  → pixel_unpack → rgb2dvi
                              ▼
                          PYNQ HDMI OUT ──线 B──► HDMI 采集卡 ──USB──► 笔记本
```

**不经过帧缓冲**：`pixel_pack` 的输出直接进内核，内核输出直接回 `pixel_unpack`，
原 PYNQ base overlay 里的 VDMA 环回被切断了。副作用是 PS 侧不能再用 `readframe()`
读帧——画面只能从采集卡看，这是这条通路的既定取舍。

## 文件

| 文件 | 作用 |
| --- | --- |
| `enhance_hdmi.bit` / `.hwh` | 位流（WNS +0.242 ns，LUT 63.1%，BRAM 57.5%） |
| `hdmi_enhance.py` | 加载自检：绑定、配置寄存器写入/回读、延迟寄存器方向 |
| `hdmi_live.py` | **真机演示**：应用预设、循环切换、读回实测延迟 |
| `timing_impl.rpt` / `util_impl.rpt` | 实现报告 |

## 接线（采集卡已到货）

1. **线 A**：笔记本 HDMI 输出 → PYNQ-Z2 的 **HDMI IN**；
2. **线 B**：PYNQ-Z2 的 **HDMI OUT** → 采集卡 HDMI 输入；
3. 采集卡 USB → 笔记本，用系统相机/OBS 打开，看到的是**经过增强后的画面**；
4. 笔记本显示设置里把外接屏设为 **1280×720**（PYNQ-Z2 这版 HDMI 端口的稳妥模式）。

## 跑

在板上（Jupyter Terminal 或 SSH，都要 root + venv）：

```bash
cd /home/xilinx/jupyter_notebooks/hdmi_enh

# 1) 先自检：overlay 能否加载、video 是否绑定
sudo env XILINX_XRT=/usr PATH=/usr/local/share/pynq-venv/bin:/usr/bin:/bin HOME=/root \
  /usr/local/share/pynq-venv/bin/python3 hdmi_enhance.py

# 2) 真机演示：固定一个预设
sudo env XILINX_XRT=/usr PATH=/usr/local/share/pynq-venv/bin:/usr/bin:/bin HOME=/root \
  /usr/local/share/pynq-venv/bin/python3 hdmi_live.py --preset document

# 3) 录视频用：每 4 秒换一个预设，采集卡里能直接看到画面变化
sudo env XILINX_XRT=/usr PATH=/usr/local/share/pynq-venv/bin:/usr/bin:/bin HOME=/root \
  /usr/local/share/pynq-venv/bin/python3 hdmi_live.py --cycle 4
```

脚本会打印：

```text
input detected: 1280x720 @60.0 Hz
[12:34:56] preset document  cfg=0x0c40c014 0x00000000
           latency: 16 pixel clocks (~0.112 us at 142.857 MHz)
```

`latency` 是内核流水线填充延迟（两个时间戳相减），**不是**端到端延迟；端到端还要加
HDMI 输入/输出链路，那一段只能在采集卡上肉眼/录屏评估。

## 没有画面时先查什么

| 现象 | 查 |
| --- | --- |
| `input mode: None` | 线 A 是否插紧；笔记本是否真的在往外送（扩展模式而不是仅内置屏） |
| 有输入但仍黑屏 | 采集卡是否选对了信号源；PYNQ 是否被别的程序占用 |
| 画面撕裂/闪烁 | 笔记本输出模式是否超过 PYNQ 能力（先降到 720p60） |
| `TRI = 0xffffffff` 看着奇怪 | 固定方向通道的 TRI 寄存器无意义，方向由位流参数决定 |

## 边界

- 这条通路**没有**通过 PYNQ 读回像素，因此"逐位一致"的证据来自 DMA 通路
  （`board/enhance_dma/`，8 个预设 0/2764800）；
- 内核延迟在 DMA 通路上实测 16 个像素时钟；HDMI 版用同一份 RTL 与同一时钟域
  （clk_142M），像素率 74.25 Mpixel/s 下 II=1 有 1.9 倍余量。
