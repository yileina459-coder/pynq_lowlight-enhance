# 低延迟视觉增强终端（PYNQ-Z2）

参赛厂商：AMD

参赛平台：AMD 7 Series FPGA / Zynq-7000 SoC（实际使用 PYNQ-Z2，XC7Z020）

开发方向：AMD 自主选题（初级组）

作品名称：低延迟视觉增强终端

作品简介：面向低视力人群的阅读辅助——**不经过帧缓冲**，像素边走边算，端到端延迟约一行，
而不是一帧。核心算子 `enhance`（局部对比 → 色调曲线 → 二值/反色 → 分屏）由 Vitis HLS 实现，
59 bit 参数在运行时由 PS 下发；参数含清晰度、拐点、双段增益、二值阈值、反色/单色、分屏位置。

算子族另含 Sobel、高斯、锐化三个卷积核，用于构成"同一算法软硬件对比"的证据：AXI-DMA 通路
上已做到与 numpy 黄金模型**逐位一致**，并测出 PS 3108 ms/帧 vs PL 15.8 ms/帧（196.7×）。
色彩空间转换复用 PYNQ 官方 IP。

## 当前状态

进度主表见 [`docs/roadmap.md`](docs/roadmap.md)，环境事实见 [`docs/env.md`](docs/env.md)，
设计报告见 [`report/design_report.md`](report/design_report.md)。

- [x] 初始化仓库与目录结构
- [x] 工具链打通（Vivado / Vitis HLS 2026.1，冒烟工程见 `build/smoke/`）
- [x] 流式算子：Sobel、Gaussian、Sharpen（均 II=1、C 仿真 0 误差、7 ns 下估计 194.59 MHz）
- [x] 黄金参考与逐位比对工具（`sim/common/image_ops.py` + 各算子的 `golden_*.py`）
- [x] DMA 版 Overlay 位流（`board/dma_sobel/`，WNS +3.086 ns）
- [x] HDMI 版 Overlay 构建流程（重建 PYNQ base overlay 并插入算子，`build/overlay_hdmi/`）
- [x] 通用 PYNQ Skill 三件（`skill/`）
- [x] HDMI 版 Overlay 位流（WNS +0.207 ns @142.857 MHz，`.hwh` 离线校验通过）
- [x] 板上实测：DMA 回环 **逐位一致**（0/2764800 通道），整帧 15.8 ms/帧
- [x] PS/PL 对比数据：3108.4 ms → 15.8 ms（**196.7×**），见 `report/comparison.md`
- [x] HDMI overlay 在板上加载成功、`pynq.lib.video` 绑定正常
- [x] 增强核 `enhance`：C 仿真两种配置各 9216 拍 **0 误差**、II=1、估计 Fmax 194.59 MHz、
      BRAM 3 / DSP 2 / FF 2168 / LUT 1659（3%）
- [x] 增强核 **已在板上逐位验证**：8 个预设各 0/2764800 通道不一致，15.6 ms/帧
      （`board/enhance_dma/`，走 AXI-DMA，不需要显示器）
- [x] 新增 `document` 预设：保住极性的暗页提亮（原 `reading` 在暗页上会把黑白翻转，
      对比度 +41 → −51；新预设 → **+158**，见 `sim/enhance/tune_document_preset.py`）
- [x] **增强核在 HDMI 通路上实时工作**：`board/hdmi_stream_enhance/`，WNS **+0.171 ns**；采集卡实测 640×480、延迟 **21 个像素时钟**、运行期预设切换四张证据截图在 `evidence/`
- [x] **Jupyter 交互面板**：`board/enhance_dma/panel.ipynb`（8 预设一键切换、
      实时显示帧时间/延迟/逐位比对，走 DMA 通路，不需要显示器）
- [x] **HDMI 输出打通并定位到硬件上限**（完整推导见 `docs/hdmi_status.md`）：
      这块 PYNQ-Z2 的 HDMI 输出只有 **640×480** 能工作（800×600/720p/1080p 一帧都不消费、
      不产生 TMDS，原厂 `base.bit` 行为相同）；HDMI 输入又无法工作在 640×480
      （`dvi2rgb` 的 `kClkRange` 只接受 1/2/3，25.175 MHz 需要 5 档）。
      因此帧源改为 **VDMA**：PS 写帧 → VDMA → 内核 → HDMI OUT，内核仍在真实像素通路上
- [x] **修掉 HLS 配置锁存问题**：自由运行内核的 6 个配置参数被 HLS 在 prologue 锁存
      （生成 RTL 里 `binarize_read_reg_*` 即证据）；用 `enh_rst_gate` 让 PS 复位内核，
      预设切换后重新采样，代价是当帧花屏一帧
- [ ] HDMI **直通**（笔记本 → 板子 → 显示）受上述两个硬件限制阻塞，不再作为交付路径
- [x] 内部图案源 overlay（`board/hdmi_pattern/`，不依赖任何外部输入）
- [x] **流水线延迟实测：16 个像素时钟 = 160 ns @100 MHz**（`axis_cycle_stamp` 在内核前后各
      打一次时间戳；720p60 的一行是 17.2 µs，所以延迟只有一行的 1%，原来说的「约一行」是上界）
- [ ] 端到端延迟与功耗实测：采集卡已到，但 HDMI 直通受硬件限制（见上），只能测 PL 内部延迟（21 拍）；功耗需外部功率计
- [x] **参数化与 UI**：8 预设运行期切换，两条通路各有一个 Jupyter 面板 —— `board/enhance_dma/panel.ipynb`（DMA，逐位比对）与 `board/hdmi_stream_enhance/notebooks/hdmi_panel.ipynb`（HDMI，点按钮切预设）
- [x] **一页英文 A4 海报**：`report/poster/poster.pptx`（由 `make_poster.py` 生成，配图为板子 HDMI 输出的 2×2 采集拼图）；拿到 AMD 官方模板后可直接套版

## 技术栈

- 硬件平台：PYNQ-Z2（Zynq-7000 XC7Z020）
- 开发工具：Vivado / Vitis 2026.1（赛规允许 2025.2；本项目全程 2026.1）
- PL 实现：Vitis HLS（3 个自研卷积核）+ PYNQ 官方 IP（HDMI 子系统、色彩空间转换）
- PS 实现：Python、Jupyter Notebook、PYNQ Overlay
- UI：ipywidgets（待做）

## 目录结构

```
.
├── README.md                 # 项目简介 + 状态清单 + 复现步骤
├── docs/                     # 架构、路线图、环境基线、HDMI 全部实测记录、提交清单
├── src/
│   ├── hls/                  # enhance（主算子 + 有界版）、sobel/gaussian/sharpen（算子族）
│   └── rtl/                  # axis_cycle_stamp（延迟/拍数）、enh_cfg_split、enh_rst_bridge、
│                             # video_pattern_gen、axis_mux3、edid/
├── sim/                      # numpy 黄金模型、离线预演、预设调参、性能对比表
├── build/
│   ├── smoke/                # 工具链冒烟
│   ├── hls/                  # 每个算子的 HLS 工程脚本（流式 + 有界）
│   ├── overlay_dma/          # DMA 版 overlay（Sobel）
│   ├── overlay_enhance/      # DMA 版 overlay（enhance，8 预设验证）
│   ├── overlay_hdmi/         # HDMI 版 overlay（Sobel）
│   ├── overlay_hdmi_enhance/ # HDMI 版 overlay（enhance + 复位桥 + EDID 定制）
│   └── rtl/                  # 独立 RTL 的综合脚本
├── board/
│   ├── dma_sobel/            # DMA 版：Sobel 逐位比对
│   ├── enhance_dma/          # 增强核：8 预设板上逐位比对 + Jupyter 面板
│   ├── hdmi_stream/          # HDMI 版（Sobel 算子族）
│   ├── hdmi_stream_enhance/  # **HDMI 版主通路**：640×480、21 拍、演示循环的 7 档预设可切
│   │   ├── evidence/         #   采集卡截图（真机证据）
│   │   ├── diagnostics/      #   21 个排查脚本，按"回答什么问题"索引
│   │   └── notebooks/        #   Jupyter 版验证与演示
│   ├── hdmi_pattern/         # 内部图案源（不依赖任何外部输入）
│   └── ps_baseline/          # PS 软件基线
├── data/                     # 测试图与各算子黄金参考
├── skill/                    # 5 个可复用 Skill + 踩坑清单
├── tools/                    # 工具链入口 + 文档/位流/海报/EDID 检查脚本
└── report/                   # 设计报告、协作记录、校赛材料、海报
```

## 复现步骤

前置：Vivado / Vitis HLS 2026.1，PYNQ-Z2 + PYNQ 3.1.x 镜像。环境细节与已知坑见
[`docs/env.md`](docs/env.md)。

```powershell
# 1) 工具链冒烟（各约 1 分钟）
cd build\smoke\vivado ; ..\..\..\tools\env\vivado.bat -mode batch -nojournal -nolog -source synth_smoke.tcl
cd build\smoke\hls    ; ..\..\..\tools\env\vitis_hls.bat -f run_hls.tcl

# 2) 算子（C 仿真 + 综合 + 导出 IP），每个约 1-2 分钟
tools\env\vitis_hls.bat -f build\hls\enhance\run_hls.tcl   # 主算子
tools\env\vitis_hls.bat -f build\hls\sobel\run_hls.tcl
tools\env\vitis_hls.bat -f build\hls\gaussian\run_hls.tcl
tools\env\vitis_hls.bat -f build\hls\sharpen\run_hls.tcl

# 3) 软件黄金参考
python sim\sobel\golden_sobel.py  --generate-test-image data\images\test_720p.png
python sim\sobel\golden_sobel.py    --input data\images\test_720p.png --reference data\reference\sobel_720p.png    --border wrap
python sim\gaussian\golden_gaussian.py --input data\images\test_720p.png --reference data\reference\gaussian_720p.png --border wrap
python sim\sharpen\golden_sharpen.py   --input data\images\test_720p.png --reference data\reference\sharpen_720p.png  --border wrap

# 4) Overlay 位流（DMA 版约 12 分钟；HDMI 版约 60 分钟，含 PYNQ 源码拉取与 HLS IP 重建）
build\overlay_dma\build.bat
build\overlay_hdmi\build.bat

# 5) 上板（把 board\<version>\ 下的文件传到板子同一目录）
python3 sobel_dma.py                     # DMA 版：期望 COMPARE PASS (bit-exact)
python3 hdmi_sobel.py --seconds 10       # HDMI 版：期望 RESULT: OK（画面需显示器/采集卡）
python3 ps_sobel.py --input test_720p.png --metrics metrics.csv
```

## 评分对应证据

| 评分项 | 对应提交物 |
| --- | --- |
| 创新性与应用价值 30 | 完整 HDMI 视频处理系统、双通路验证方法、软硬件对比 |
| 性能与资源优化 20 | `sim/perf/make_comparison.py` 生成的对比表 + `metrics.csv` 原始数据 |
| 功能正确性与设计完整性 20 | 三个算子的 C 仿真（0 误差）、综合报告、DMA 逐位比对、HDMI 上板 |
| 大模型协作与技能包 15 | [`report/ai_collaboration_log.md`](report/ai_collaboration_log.md) + `skill/` |
| 文档质量与可复现性 15 | 本 README + `docs/` + 全脚本化构建 + 设计报告 |
