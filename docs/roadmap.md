# 开发路线图

目标：2026 年全国大学生嵌入式芯片与系统设计竞赛 FPGA 创新设计赛道 · AMD 自主选题赛道（初级组）。
作品：PYNQ-Z2 上的 HDMI 实时视频处理流水线。

本文件是唯一的主进度表。每完成一项，就在"状态"列改成 `DONE` 并附证据路径。

## 阶段总览

| 阶段 | 内容 | 验收标准（可验证） | 对应评分项 | 状态 |
| P4b | enhance 核进 overlay | 位流 + 加载/配置/延迟验证 | 创新性 + 完整度 | **已完成**（真机画面另见下） |
| P4c | HDMI 输出打通 | OUT 产生 TMDS 并出图 | 创新性 | **已完成**：640×480、延迟 21 拍、7 档预设运行期可切（`docs/hdmi_status.md`） |
| --- | --- | --- | --- | --- |
| P0 | 工具链基线 | Vivado 综合 + HLS 仿真/综合/导出 IP 全通过 | 可复现性 | **DONE**（`build/smoke/`、`docs/env.md`） |
| P1 | 官方 HDMI 回环 | 板子上 `hdmi_in.tie(hdmi_out)` 出图，记录分辨率/帧率证据 | 功能正确性 | **已测**：1080p 能锁输入；输出侧只有 640×480 能驱动（原厂位流同样如此） |
| P2 | 第一个 HLS 算子（Sobel） | C 仿真与 OpenCV 黄金参考逐像素一致；C 综合 II=1 | 功能正确性 | **C 仿真 + 综合 DONE**，上板待 P3 |
| P3 | 自定义 Overlay（流式主线） | 自定义算子插在视频流中间并实时出图 | 创新性 + 完整度 | **已完成（VDMA 供帧）**：`board/hdmi_stream_enhance/` |
| P4 | 算子族 + 参数化 + UI | 4 个算子可由 PS 侧切换/调参，UI 可交互 | 完整度 + 创新 | 未开始 |
| P5 | PS vs PL 对比数据 | 帧率/延迟/吞吐/资源/功耗对比表，脚本可复跑 | 性能与资源优化 20 分 | 未开始 |
| P6 | 交付物 | skill 4 件、协作记录、报告、英文 A4 海报、复现说明 | 15 + 15 分 | 未开始 |

## 关键决策（需要你确认，我先按推荐值推进）

| 决策 | 推荐 | 理由 |
| --- | --- | --- |
| 目标分辨率 | **720p60**（1080p 作为加分项） | PYNQ-Z2 的 HDMI 前端口受差分引脚速率限制，官方只保证到 720p；架构按参数化行缓冲写，后续升 1080p 只改参数 |
| 主展示路线 | **Pipeline（AXI-Stream 直通）** | 延迟最低、最能体现"实时"，也是指南点名的实时路线 |
| 对比路线 | **DMA 批处理**（若时间允许）+ **PS 纯 Python 版**（必做） | 20 分要求"PS 软件 vs PL 加速"的量化对比；PS 版同时充当黄金参考 |
| 算子范围 | Sobel → 高斯 → 锐化 → 色彩空间转换，共 4 个 | 指南原话列出的四个算子，覆盖卷积与逐像素两类结构 |
| 实现方式 | HLS 为主，个别模块用手写 RTL（如行缓冲/流控） | 兼顾开发效率与"必须有自己设计的硬件" |

## 各阶段详细定义

### P0 工具链基线 — DONE

- 入口脚本：`tools/env/vivado.bat`、`tools/env/vitis_hls.bat`
- 冒烟工程：`build/smoke/vivado/`、`build/smoke/hls/`
- 事实记录：`docs/env.md`

### P1 官方 HDMI 回环

目的：把"板子 + 镜像 + HDMI 源 + 显示器"这条链路先证明是好的，后面所有问题都能归因到自己的设计。

- 前置：PYNQ-Z2 到手、SD 卡烧好 PYNQ 镜像（记录版本号）、HDMI 输入源（笔记本/相机）、HDMI 显示器
- 动作：`BaseOverlay("base.bit")` → `hdmi_in.configure()` → `hdmi_out.configure(mode)` → `tie()`
- 证据：`board/p1_loopback/` 下放 notebook、`hdmi_in.mode` 打印（分辨率/帧率/像素时钟）、屏幕拍照
- 验收：显示器稳定出图 ≥ 10 分钟无闪断

### P2 第一个 HLS 算子（Sobel）— C 仿真与综合 DONE

- 代码：`src/hls/sobel/`（`sobel.cpp`、`sobel.hpp`、`tb_sobel.cpp`）
- 构建：`build/hls/sobel/run_hls.tcl`
- 验证：`sim/sobel/golden_sobel.py`（Python 黄金参考 + bit-exact 比对）
- 结果：C 仿真 9216 拍 0 误差、侧带信号完好；II=1；Fmax≈141.9 MHz；
  BRAM 3 / DSP 2 / FF 583 / LUT 809；IP 已导出
- 剩余：上板（合并到 P3 一起验证）

### P3 自定义 Overlay（拆成 3a / 3b 两步降风险）

#### P3a DMA 版 overlay（进行中，先做，不需要显示器）

目的：不用 HDMI、不用显示器，先证明算子在一块真板子上是对的，并拿到第一份真实性能数据。

```text
PS Python <-> DDR <-> AXI DMA (MM2S/S2MM) <-> sobel_stream
```

- 构建：`build/overlay_dma/build.bat`（一行命令：解包 HLS IP → 建块设计 → 实现 → 出位流 → 拆出 .bit/.hwh）
- 上板：`board/dma_sobel/`（`sobel_dma.py` + `demo.ipynb`，逐行 DMA 传输，结果与黄金参考逐位比对）
- 离线预演：`sim/sobel/test_sobel_dma_offline.py`（假 DMA 用 numpy 复现核行为，先验证主机侧脚本）
- 验收：板上 `COMPARE PASS`（0 个通道不一致），`metrics.csv` 有第一条真实数据
- 限制：按行传输，DMA 每次传输的固定开销会让帧率显著低于真实流式性能
- **DONE（板卡实测）**：位流 WNS +3.086 ns；板上 `COMPARE PASS (bit-exact)`，0/2764800 不一致；
  逐行传输 659 ms/帧、**整帧传输 15.8 ms/帧（63.45 fps、58.5 Mpixel/s）**，
  相对 PS numpy（3108 ms/帧）为 **4.7×（逐行传输）/ 196.7×（整帧传输）**
- 关键修复三步：① 自由运行核在流结束时不排空 → 换有界核 `sobel_bounded`（`ap_ctrl_hs`）；
  ② 有界核的 AXI-Lite 控制口漏接 → 控制互联加第二路主口；
  ③ DMA 长度寄存器默认 14 位（16 KB）→ 改为 23 位，才可能整帧传输
  （完整记录见 `docs/dma_investigation.md`）

#### P3b HDMI 流式 overlay（主展示形态，需要显示/采集）

**已从"预研"推进到"可构建"**，详细结论见 `docs/p3b_plan.md`：

- base overlay（4448 行、Vivado 2024.1 生成）在 2026.1 里重建成功，只需 3 个补丁
  （版本门禁、IP 仓库绝对路径、`PFM_NAME` 字面量）；
- PYNQ 的 5 个 HLS 视频 IP 用 Vitis HLS 2026.1 重新打包通过；
- Sobel 核直接对接 `pixel_pack` 的 32 位流（`SOBEL_PIX_W=32`），不需要位宽转换；
- 切断 VDMA 环回，`video/hdmi_in/out_stream → sobel_0 → video/hdmi_out/in_stream`；
- 内核在 7 ns 目标下估计 Fmax 194.59 MHz（视频时钟 142.86 MHz）。

- 构建：`build/overlay_hdmi/build.bat`（拉源码 → 打补丁 → 重建 HLS IP → 块设计 → 插入 → 实现）
- 产物：`board/hdmi_stream/`（`sobel_hdmi.bit`、`.hwh`、`hdmi_sobel.py`）
- **构建完成**：`sobel_hdmi.bit` 已生成，WNS +0.207 ns @142.857 MHz，`.hwh` 离线校验通过
- 验收：板上 overlay 能加载、HDMI 输入锁定、输出出图（需显示器或采集卡）

### P4 算子族 + 参数化 + UI（含新的主算子 enhance）

- 已完成：Sobel、Gaussian 两个流式核（均 II=1、0 误差、7 ns 下 194 MHz）
- 待做：锐化（3×3 拉普拉斯/非锐化掩模）、色彩空间转换
- 参数化路线（二选一，倾向 A）：
  - **A. 多核 + 流切换**：手写一个 AXI-Stream 3 选 1 切换器（带 AXI-Lite 寄存器），
    4 个算子并排例化，PS 写寄存器切换。切换器是本项目唯一的手写 RTL，也是"自己设计硬件"的证据；
  - B. 单核参数化：把阈值/增益做成 AXI-Lite 寄存器（要放弃 `ap_ctrl_none`，改动较大）。
- 另一个确定的改进：**TLAST 生成器**（手写 RTL，按行宽计数插 `TLAST`），
  让 DMA 版可以整帧传输而不是逐行传输，帧率预计提升一个数量级
- PS 侧：`src/ps/` 下 overlay 驱动封装 + ipywidgets UI
- 验收：UI 上切算子/调参，画面实时变化，无花屏无撕裂

#### P4b 增强核进 overlay（主线，10/22 采集卡到货后）

`enhance` 已完成 C 仿真（两种配置各 9216 拍 0 误差）与综合（II=1、194.59 MHz、
BRAM 3 / DSP 2 / FF 2168 / LUT 1659），**尚未进位流**。

- 集成方式：替换 `board/hdmi_stream` 里的 `sobel_0`，参数走一个 `axi_gpio` 双通道
  （2×32 bit > 59 bit，核本体不加 AXI-Lite）；
- 风险：HDMI overlay 现有 WNS 只有 +0.207 ns，enhance 估计 194.59 MHz，理论上够，
  但需要实现后看真实时序；
- **已完成的一半（10/19）**：增强核本身已在板上证明——用 AXI-DMA 整帧跑 8 个预设，
  每个都与 numpy 黄金模型逐位一致（0/2764800），15.6 ms/帧；见 `board/enhance_dma/`。
  剩下的是"接上 HDMI 看画面"，那一步才依赖采集卡；
- **止损线 2026-11-01**：若届时时序不收敛或功能未通，回退到现有 Sobel 版 HDMI 位流，
  用 DMA 通路 + 算子族作为技术证据，`report/school_round.md` 已按此口径写；
- 提交截止 **2026-11-04**。

### P5 性能与资源对比

必测五类数据（每项都要有复跑脚本与原始日志）：

| 指标 | 测法 |
| --- | --- |
| 帧率 | PL 侧帧计数寄存器 + PS 侧时间戳，双口径 |
| 延迟 | HDMI-In 打时间戳 → HDMI-Out 计数，或帧缓冲计数差 |
| 吞吐 | AXI-Stream 有效像素率（像素/秒） |
| 资源 | 综合/实现报告 LUT/FF/BRAM/DSP |
| 功耗 | 板级输入功率（外部表或无表时的估算口径，需写清测量边界） |

- 脚本：`skill/perf_collect`（入库）+ `sim/perf/make_comparison.py`（生成对比表，已完成并测过）
- 验收：PS 软件版与 PL 加速版在同一输入下跑同一算子，数据可复现

### P6 交付物

- `skill/`：4 个通用 Skill（Overlay 加载校验、DMA 搬运与缓存一致性、黄金参考比对、性能/资源自动采集），每个写清适用范围/用法/失效条件/已验证效果
- `report/`：设计报告 + **大模型协作记录**（提示词、回答、自我纠错的完整轨迹）
- `README.md`：从零复现步骤
- 决赛：一页英文 A4 海报（AMD 模板）

## 风险清单

| 风险 | 影响 | 应对 |
| --- | --- | --- |
| 2026.1 生成的 `.bit/.hwh` 与 PYNQ 镜像（2024.1 构建）不兼容 | P3 可能整条卡住 | P3 第一步先做"原样重建 base overlay"验证版本链；不行则退回 2025.2 或改用 2024.1 构建 overlay |
| BASIC 许可不覆盖某些 IP | 无法综合 | 提前确认所需 IP 的许可等级，必要时换等效自写逻辑 |
| XC7Z020 资源不够 4 算子全流水 720p | 只能降规格 | 算子串行复用一套行缓冲、按需例化；先做资源预算再动手 |
| 板卡/HDMI 源未就绪 | P1 阻塞 | 先用 P2 的离线流程（仿真 + 综合）推进，不等硬件 |
| 目录/文件名出现中文 | 违反赛规 | 提交前用脚本检查路径字符集 |

## HDMI 分辨率结论（2026-10-22 实测）

- **输入**：能锁 1080p（`_capture` 报 `1920x1080@60`），前提是 HPD 已拉高、EDID 正常。
- **输出**：只有 **640×480** 能驱动；800×600 / 720p / 1080p 下 VDMA 一帧都不消费、
  不产生 TMDS。用原厂 `base.bit` 测同样结果，属板子物理上限（HDMI 口无缓冲直连 PL）。
- 因此"输入输出同分辨率的直通"不可行，交付演示改由 VDMA 供帧；
  计划中的 720p60 目标按实测调整为 **640×480 交付 + 参数化保留**。
