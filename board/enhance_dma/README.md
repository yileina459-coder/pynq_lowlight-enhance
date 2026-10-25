# enhance_dma — 增强核的板级逐位验证（不需要显示器）

这个目录解决一个具体问题：**HDMI 采集卡没到货，但增强核是否算对，不必等它**。

把一帧送进 `enhance_bounded`，经 AXI-DMA 读回来，与 numpy 黄金模型逐通道比对。
零容差，和 Sobel 通路用的是同一把尺子。

## 为什么用"有界"版本

`src/hls/enhance/enhance.cpp` 是自由运行的流式核（`ap_ctrl_none` + 无限循环），
那是 HDMI 通路需要的形状。但它在板上有个已测到的性质：**输入一停，流水线停在读端口，
最后几拍出不来**，DMA 因此永远收不到 TLAST（见 `docs/dma_investigation.md`）。

所以 DMA 路线用 `enhance_bounded`（`ap_ctrl_hs` + 像素数 + 行宽），一次调用处理
恰好 N 个像素、处理完才拉 `ap_done`；59 位配置也改走 AXI-Lite，PS 可以每个预设重写一次。

## 怎么跑

板上（PYNQ 3.1.1，Jupyter 以 root 运行，python 必须用 venv 里的那个）：

```bash
cd /home/xilinx/jupyter_notebooks/enhance_dma
sudo env XILINX_XRT=/usr PATH=/usr/local/share/pynq-venv/bin:/usr/bin:/bin HOME=/root \
  /usr/local/share/pynq-venv/bin/python3 enhance_dma.py
```

期望输出：

```text
  register map of enhance_0: OK (12 registers)
  pass       15.9 ms   mismatched 0/2764800   max|diff| 0
  clarity    15.8 ms   mismatched 0/2764800   max|diff| 0
  reading    15.8 ms   mismatched 0/2764800   max|diff| 0
  ...
COMPARE PASS (bit-exact) for all presets
```

## 一个关于预设的实测结论

`reading` 预设（knee=48）在暗页上会**把黑白翻转**：纸面（低于拐点）被 ×5.5 提亮到 114，
而字迹（高于拐点）被压向拐点停在 63，于是字比纸暗。在暗页上实测：

```text
            字迹            纸面          对比度
输入         62.7            21.4          +41.3
reading      62.8           114.1          -51.3   ← 极性翻转
document    252.0            94.1         +158.0   ← 新增预设
```

`document` 预设的 kneee 大于纸面亮度，于是整页落在同一段斜率上，极性得以保持。
参数由 `sim/enhance/tune_document_preset.py` 在可复现的暗页上搜索得到（评分函数：
正对比度、少黑像素、少过曝）。**这是合成页上的结果，真实画面到货后应重新标定。**

## 交互面板

`panel.ipynb` 是给人看的那一层：下拉选预设、按钮跑一次或基准 20 帧，
右边显示硬件真实输出图与三行数字（帧时间 / 延迟 / 逐位比对）。

```bash
# 在 Jupyter 里打开 panel.ipynb，或命令行先跑一遍自检：
python3 panel_selftest.py
```

它不是新的证据来源——所有数字都来自 `enhance_dma.py` 同一套代码路径，
面板只是让"参数化"和"低延迟"变成可以当场点出来的东西（也方便录演示视频）。

## 目录里还有

- `enhance_dma.bit` / `.hwh`：位流（由 `build\overlay_enhance\build.bat` 生成，约 12 分钟）
- `enhance_dma.py`：本文件描述的那个测试，同时写 `metrics_enhance.csv`
- `evidence/`：板上回来的输出图与前后对比图

## 测试图

`data/images/test_dim_720p.png` 是脚本生成的暗光文字页（平均亮度 28），
由 `sim/enhance/make_dim_page.py` 复现，种子固定 —— 板上、黄金模型、报告插图看的是同一张。

## 已知边界

- 这条通路证明的是**算法与集成**，不证明 HDMI 时序；HDMI 真机画面与延迟见
  [`../hdmi_stream_enhance/`](../hdmi_stream_enhance/)，端到端延迟受本板 HDMI 直通限制仍未测；
- `enhance_bounded` 没有单独的 C 仿真（流式版本的 csim 覆盖了同一套算术），
  它的正确性由这里的板上逐位比对来证明 —— 这比 csim 更强，但不是"仿真也过了"。
