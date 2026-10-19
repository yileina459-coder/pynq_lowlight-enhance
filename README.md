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
- [ ] 增强核进 overlay、端到端真机画面（等 HDMI 采集卡，预计 10/22 到货）
- [ ] 延迟与功耗实测（流水线延迟 <1 行、端到端 <50 ms 为目标）
- [ ] 参数化与 UI（算子切换、阈值/增益调节）
- [ ] 决赛用一页英文 A4 海报

## 技术栈

- 硬件平台：PYNQ-Z2（Zynq-7000 XC7Z020）
- 开发工具：Vivado / Vitis 2026.1（赛规允许 2025.2；本项目全程 2026.1）
- PL 实现：Vitis HLS（3 个自研卷积核）+ PYNQ 官方 IP（HDMI 子系统、色彩空间转换）
- PS 实现：Python、Jupyter Notebook、PYNQ Overlay
- UI：ipywidgets（待做）

## 目录结构

```
.
├── README.md                 # 项目简介 + 复现步骤
├── docs/                     # 架构、路线图、环境基线、HDMI 移植记录、参考资料
├── src/                      # HLS 源码：enhance（主算子）、sobel/gaussian/sharpen（算子族）
├── sim/                      # 软件黄金模型、比对脚本、离线预演、性能对比表
├── build/                    # 可复现构建脚本 + 综合实现报告
│   ├── smoke/                # 工具链冒烟（Vivado / Vitis HLS）
│   ├── hls/                  # 每个算子的 HLS 工程脚本
│   ├── overlay_dma/          # DMA 版 overlay 构建
│   └── overlay_hdmi/         # HDMI 版 overlay 构建（含 PYNQ base overlay 移植）
├── board/                    # 上板脚本与实测输出
│   ├── dma_sobel/            # DMA 版：逐位比对
│   ├── hdmi_stream/          # HDMI 版：实时出图
│   └── ps_baseline/          # PS 软件基线
├── data/                     # 测试图与各算子的黄金参考
├── skill/                    # 可复用 Skill（overlay_check / golden_compare / perf_collect）
├── tools/                    # 工具链入口脚本（Vivado / Vitis HLS 包装）
└── report/                   # 设计报告 + 大模型协作记录
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
