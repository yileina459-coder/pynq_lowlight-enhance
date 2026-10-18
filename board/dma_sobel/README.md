# DMA 验证（不需要显示器）

把测试图从 DDR 送进 FPGA 的 Sobel 核，再读回来和笔记本上算出的黄金参考逐位比对。
**全程不需要 HDMI、不需要显示器**，只用网线和 Jupyter。

## 这一版验证了什么

```text
  SD 卡上的 PNG
       │  numpy 打包成 32-bit 字 {R,G,B}
       ▼
  PS 侧 Python ──AXI DMA(MM2S)──> sobel_stream ──AXI DMA(S2MM)──> PS 侧 Python
                                                                     │
                                                    逐像素比对 <──────┘
```

- HLS 核在真实器件上跑出来的结果和软件参考**完全一致**（0 个通道不一致）
- 顺带得到第一条真实性能数据：帧率、像素吞吐（写进 `metrics.csv`）

## 板上要放的文件

从仓库的 `board/dma_sobel/` 上传到板子的 `/home/xilinx/jupyter_notebooks/sobel_dma/`：

| 文件 | 作用 |
| --- | --- |
| `sobel_dma.bit` | 位流 |
| `sobel_dma.hwh` | 硬件描述（PYNQ 靠它解析寄存器地址） |
| `sobel_dma.py` | 测试脚本 |
| `test_720p.png` | 输入测试图（来自 `data/images/`） |
| `sobel_720p.png` | 黄金参考（来自 `data/reference/`） |

两个 PNG 可以先用仓库里的同名文件，也可以自己生成：

```bash
python sim/sobel/golden_sobel.py --generate-test-image data/images/test_720p.png
python sim/sobel/golden_sobel.py --input data/images/test_720p.png \
    --reference data/reference/sobel_720p.png --border wrap
```

## 怎么跑

**板上实测过的调用方式**（PYNQ 3.1.1 的 Jupyter 以 root 运行，XRT 设备只有 root 能开，
且 python 必须用 venv 里的那个）：

```bash
cd /home/xilinx/jupyter_notebooks/sobel_dma
sudo env XILINX_XRT=/usr \
     PATH=/usr/local/share/pynq-venv/bin:/usr/bin:/bin HOME=/root \
     /usr/local/share/pynq-venv/bin/python3 sobel_dma.py
```

如果你就在 Jupyter 的 Notebook / Terminal 里跑，环境已经是对的，直接
`python3 sobel_dma.py` 即可。

期望最后几行（板上实测，2026-10-18）：

```text
  kernel control: yes (bounded, ap_ctrl_hs)
  frame 3/3: 15.7 ms (58.80 Mpixel/s)
COMPARE PASS (bit-exact)
throughput: 63.45 frame/s, 58.47 Mpixel/s
```

默认是**整帧一次传输**（1 次核启动 + 2 次 DMA 传输）。想复现早期的逐行模式、
对比软件开销，加 `--per-row`：那种模式是 659 ms/帧，慢 41 倍。

## 为什么要"有界"版本的核

DMA 路线的核是 `sobel_bounded`（`src/hls/sobel/sobel_bounded.cpp`）：带
`ap_ctrl_hs` 和一个 `n_pixels` 参数，每次调用处理恰好 N 个像素、处理完才拉高 `ap_done`。

之前用的是 HDMI 那个自由运行的核（`ap_ctrl_none` + 无限循环），在板上的表现是：
传输永远差一个 AXI burst 收不了尾。逐档测量后确认根因是**流结束时流水线没有排空**
——给 1280 拍输入，出来的不足 1280 拍，DMA 于是永远等不到 TLAST。
完整数据和推理见 [`docs/dma_investigation.md`](../../docs/dma_investigation.md)。

所以脚本里每传一行之前会先启动一次核：

```python
kernel.start(width)     # 写 n_pixels，然后 ap_start
dma.sendchannel.transfer(...)
dma.recvchannel.transfer(...)
kernel.wait_done()      # 轮询 ap_done
```

HDMI 路线不受这个问题影响（视频流永不停），那边继续用自由运行的核。


**方式二：Notebook**

打开 `demo.ipynb` 从上到下运行，效果相同。

## 参数

```bash
python3 sobel_dma.py --frames 3           # 默认跑 3 帧，比较第 3 帧
python3 sobel_dma.py --no-compare        # 只测吞吐，不做比对
python3 sobel_dma.py --width 1280 --height 720
```

**为什么要跑第 3 帧才比较**：行缓冲上电是 0，第 1 帧顶部两行必然是"脏"的；
到第 3 帧行缓冲里已经是真实数据，核进入稳态。黄金参考用 `--border wrap`
生成，正是描述稳态下"上一帧的最后两行"这个行为。

## 为什么是一行一次 DMA

HLS 核把 `TLAST` 当作行结束（HDMI 路线上 `pixel_pack` 就是这么给的）。
整帧一次传输的话，921600 个像素会被当成"一行 921600 像素"，列计数器溢出。
所以这一版按行传输（720 次/帧）。这样做有两个代价，都记在下面：

- 每次传输有固定开销，所以这里测出的帧率**低于**真实流式性能；
- 真正的实时性能要到 HDMI 流式版本（P3b）才作数。

这也正是它的价值：先把"算得对不对"钉死，再谈"算得多快"。

## 常见问题

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| `Overlay` 报 `hwh` 找不到 | 两个文件不同名 | 必须都叫 `sobel_dma.*` |
| `no AXI DMA in overlay` | 位流没加载成功 | 看 Jupyter 输出的报错，确认 `.bit` 是这次构建出来的 |
| 比对大面积不一致 | 输入图和参考图不配套 | 用同一份 `test_720p.png` 重新生成参考 |
| 只有顶部两行不一致 | 比较了第 1 帧 | 跑 3 帧，比较最后一帧 |
| 传输卡死（`wait()` 不返回） | DMA 传输长度超过缓冲区 / 中断未挂 | 先用 `--frames 1` 试；看 `dmesg` |
