# 开发路线图

目标：2026 年全国大学生嵌入式芯片与系统设计竞赛 FPGA 创新设计赛道 · AMD 自主选题赛道（初级组）。
作品：PYNQ-Z2 上的 HDMI 流式视频处理流水线（VDMA 供帧，640×480@60）。

本文件是**主进度表**（2026-10-24 更新）。每完成一项就在"状态"列写 `DONE` 并附证据路径；
所有指标的唯一定义见 [`facts.md`](facts.md)。

## 阶段总览

| 阶段 | 内容 | 验收标准（可验证） | 对应评分项 | 状态 |
| --- | --- | --- | --- | --- |
| P0 | 工具链基线 | Vivado 综合 + HLS 仿真/综合/导出 IP 全通过 | 可复现性 | **DONE**（`build/smoke/`、`env.md`） |
| P1 | 官方 HDMI 回环 | 板子能锁输入、记录分辨率/帧率证据 | 功能正确性 | **已测**：输入可锁 1080p；输出只有 640×480 能驱动（原厂位流同样如此） |
| P2 | 第一个 HLS 算子（Sobel） | C 仿真与黄金参考逐像素一致；C 综合 II=1 | 功能正确性 | **DONE**：9216 拍 0 误差、II=1、194.59 MHz；上板见 P3a |
| P3a | DMA 版 overlay | 板上整帧回环与黄金参考逐位比对 | 创新性 + 完整度 | **DONE**：0/2764800、15.8 ms/帧、196.7×（`board/dma_sobel/`） |
| P3b | HDMI 版 overlay（Sobel） | 板上加载 overlay 并出图 | 创新性 | **DONE**：构建 + 加载验证（`board/hdmi_stream/`） |
| P4 | enhance 主算子 + 参数化 + 面板 | 逐位验证、运行期切预设、UI | 完整度 + 创新 | **DONE**：DMA 8 档逐位；HDMI 10 档运行期切换；两个 Jupyter 面板 |
| P4b | enhance 进 HDMI overlay | 位流 + 加载/配置/延迟验证 | 创新性 + 完整度 | **DONE**：WNS +0.206、21 拍、10 档、偏移自动标定（`board/hdmi_stream_enhance/`） |
| P4c | HDMI 输出打通 | OUT 产生 TMDS 并出图 | 创新性 | **DONE**：640×480@60 持续出图（`docs/hdmi_status.md`） |
| P5 | 性能与资源对比 | PS vs PL 对比表，脚本可复跑 | 性能与资源优化 20 分 | **DONE（功耗未测）**：`report/comparison.md`、`sim/perf/make_comparison.py` |
| P6 | 交付物 | Skill、协作记录、报告、海报、PPT、提交文案 | 15 + 15 分 | **DONE**：5 个 Skill、55 条纠错记录、设计报告、A4 海报、5/6 分钟 PPT、提交文案 |
| P7 | 提交前口径统一 | 全仓库数字一致、`check_consistency --strict` 通过 | 文档质量 | **进行中**：以 [`facts.md`](facts.md) 为基线；真机复核待板子在线 |

## 关键决策（已按实测调整）

| 决策 | 结果 | 理由 |
| --- | --- | --- |
| 目标分辨率 | 原定 720p60；**实测改为 640×480 交付** | 本板 HDMI 输出只有 640×480 能驱动；参数化行缓冲保留，换板可升 |
| 主展示路线 | **Pipeline（AXI-Stream 流式，VDMA 供帧）** | 处理延迟最低（21 拍 = 147 ns），也是指南点名的流式路线；直通受输入/输出模式不匹配阻塞 |
| 对比路线 | **DMA 整帧 + PS numpy 基线** | 20 分要求"PS 软件 vs PL 加速"的量化对比；PS 版同时充当黄金参考 |
| 算子范围 | **enhance（主）+ Sobel / Gaussian / Sharpen** | 覆盖逐像素与卷积两类结构；色彩转换复用 PYNQ IP |
| 实现方式 | HLS 为主，手写 RTL 做 SOF / 时间戳 / 配置 BRAM 等胶合 | 兼顾开发效率与"必须有自己设计的硬件" |

## 各阶段详细定义

### P0 工具链基线 — DONE

- 入口脚本：`tools/env/vivado.bat`、`tools/env/vitis_hls.bat`
- 冒烟工程：`build/smoke/vivado/`、`build/smoke/hls/`
- 事实记录：[`env.md`](env.md)

### P1 官方 HDMI 回环 — 已测

- 目的：把"板子 + 镜像 + HDMI 源 + 显示器"这条链路先证明是好的。
- 结果：输入可锁 1080p（HPD 拉高、EDID 正常）；输出只有 640×480 能驱动，
  原厂 `base.bit` 行为相同 → 板子物理上限。

### P2 第一个 HLS 算子（Sobel）— DONE

- 代码：`src/hls/sobel/`（`sobel.cpp`、`sobel.hpp`、`tb_sobel.cpp`）
- 构建：`build/hls/sobel/run_hls.tcl`
- 验证：`sim/sobel/golden_sobel.py`（Python 黄金参考 + bit-exact 比对）
- 结果：C 仿真 9216 拍 0 误差、侧带信号完好；II=1；7 ns 下估计 194.59 MHz；
  BRAM 3 / DSP 2 / FF 583 / LUT 809；IP 已导出

### P3 自定义 Overlay

#### P3a DMA 版 overlay — DONE

```text
PS Python <-> DDR <-> AXI DMA (MM2S/S2MM) <-> sobel_stream
```

- 构建：`build/overlay_dma/build.bat`
- 上板：`board/dma_sobel/`（整帧传输，结果与黄金参考逐位比对）
- 结果：WNS +3.086 ns；`COMPARE PASS`，0/2764800 不一致；逐行 659 ms/帧、
  **整帧 15.8 ms/帧（63.45 fps、58.5 Mpixel/s）**；相对 PS numpy（3108.4 ms/帧）
  为 4.72×（逐行）/ **196.7×（整帧）**
- 关键修复：① 自由运行核流结束不排空 → 换有界核 `sobel_bounded`；② 有界核 AXI-Lite 控制口漏接；
  ③ DMA 长度寄存器默认 14 位（16 KB）→ 放宽到 23 位（完整记录见 [`dma_investigation.md`](dma_investigation.md)）

#### P3b HDMI 流式 overlay — DONE

- base overlay（Vivado 2024.1 生成）在 2026.1 重建成功，只需 3 个补丁
  （版本门禁、IP 仓库绝对路径、`PFM_NAME` 字面量）；
- PYNQ 的 5 个 HLS 视频 IP 用 Vitis HLS 2026.1 重新打包通过；
- 产物：`board/hdmi_stream/`（`sobel_hdmi.bit`、`.hwh`、`hdmi_sobel.py`），WNS +0.207、加载通过

### P4 增强核 enhance + 参数化 + UI — DONE

- 算子：局部对比 → 两段色调曲线 → 二值/反色/单色 → 分屏；59 bit 参数
- 验证：C 仿真两种配置各 9216 拍 0 误差；DMA 通路 8 档各 0/2764800（15.6 ms/帧）
- 参数化：配置驻留 `cfg_bram`，内核每像素读一次；切预设一次寄存器写、不复位
- UI：`board/enhance_dma/panel.ipynb`（DMA）、`board/hdmi_stream_enhance/notebooks/hdmi_panel.ipynb`（HDMI）

### P4b 增强核进 HDMI overlay — DONE

- 集成：HLS `enhance` + HLS `sof_gen` + 配置 BRAM + EDID 定制
- 时序：**WNS +0.206 ns**、0 失败端点（含 SOF 生成器）
- 上板：640×480@60 持续出图；流水线 **21 拍 = 147 ns**；10 档运行期切换；
  150 s / 25 次切换 / 741 次写帧 0 卡顿
- 偏移：相位属于每一路像素流；启动后自动标定（本次 218），残差 0–1 px（[`output_offset.md`](output_offset.md)）

### P5 性能与资源对比 — DONE（功耗未测）

| 指标 | 结果 |
| --- | --- |
| 帧率 | PL 整帧 63.45 fps（DMA，720p）；HDMI 640×480@60 |
| 延迟 | DMA 16 拍 = 160 ns；HDMI 21 拍 = 147 ns |
| 吞吐 | 58.47 Mpixel/s（DMA 整帧） |
| 资源 | enhance：BRAM 3 / DSP 2 / FF 2168 / LUT 1659（3%） |
| 功耗 | **未测**（PYNQ-Z2 无板载功率计） |
| 端到端 | **未测**（直通未打通） |

### P6 交付物 — DONE

- `skill/`：5 个通用 Skill（Overlay 校验、DMA 搬运、黄金比对、性能采集、踩坑清单）
- `report/`：设计报告、**55 条**大模型协作记录、校赛一页、英文 A4 海报、5/6 分钟 PPT
- `README.md`：从零复现步骤；`docs/`：事实基线、HDMI 全部实测、偏移、上传、视频
- 提交文案：`report/submission_text.md`（391 字符主推版）

### P7 提交前口径统一 — 进行中

- 以 [`facts.md`](facts.md) 为唯一数字口径，改 README / 报告 / 校赛材料 / PPT / 海报；
- `tools/check_consistency.py --strict` 作为提交前门禁（新增「实时 / 偏移 / 旧档数 / 旧 WNS」等规则）；
- 待办：板子在线后复核当前 10 档表的逐位一致性（现在只验过 8 档旧表）。

## 风险清单

| 风险 | 影响 | 应对 |
| --- | --- | --- |
| 2026.1 生成的 `.bit/.hwh` 与 PYNQ 镜像（2024.1 构建）不兼容 | 上板卡住 | 已用原样重建 base overlay 验证版本链；记录在 [`p3b_plan.md`](p3b_plan.md) |
| HDMI 只能 640×480，且无法直通 | 端到端延迟无法测 | 交付改 VDMA 供帧，测 PL 内部延迟；如实写明边界 |
| 时序余量只有 +0.206 ns | 再加逻辑可能不收敛 | 交付位流不再加逻辑；三路算子并行未接入 |
| 偏移随像素流重启变化 | 每次启动画面可能偏 | 启动后自动标定 + 复测；位流层根治需重建 |
| 板卡远程、演示只能一次启动 | 调试/演示中断代价高 | 单实例 + `/tmp` 控制面；`ensure_demo.ps1`、`reset_board.ps1` |
| 目录/文件名出现中文 | 违反赛规 | 提交前用脚本检查路径字符集 |

## HDMI 分辨率结论（2026-10-22 实测）

- **输入**：能锁 1080p（`_capture` 报 `1920x1080@60`），前提是 HPD 已拉高、EDID 正常。
- **输出**：只有 **640×480** 能驱动；800×600 / 720p / 1080p 下 VDMA 一帧都不消费、
  不产生 TMDS。用原厂 `base.bit` 测同样结果，属板子物理上限（HDMI 口无缓冲直连 PL）。
- 因此"输入输出同分辨率的直通"不可行，交付演示改由 VDMA 供帧；
  计划中的 720p60 目标按实测调整为 **640×480 交付 + 参数化保留**。
