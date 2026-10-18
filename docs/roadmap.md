# 开发路线图

目标：2026 年全国大学生嵌入式芯片与系统设计竞赛 FPGA 创新设计赛道 · AMD 自主选题赛道（初级组）。
作品：PYNQ-Z2 上的 HDMI 实时视频处理流水线。

本文件是唯一的主进度表。每完成一项，就在"状态"列改成 `DONE` 并附证据路径。

## 阶段总览

| 阶段 | 内容 | 验收标准（可验证） | 对应评分项 | 状态 |
| --- | --- | --- | --- | --- |
| P0 | 工具链基线 | Vivado 综合 + HLS 仿真/综合/导出 IP 全通过 | 可复现性 | **DONE**（`build/smoke/`、`docs/env.md`） |
| P1 | 官方 HDMI 回环 | 板子上 `hdmi_in.tie(hdmi_out)` 出图，记录分辨率/帧率证据 | 功能正确性 | 待板卡 |
| P2 | 第一个 HLS 算子（Sobel） | C 仿真与 OpenCV 黄金参考逐像素一致；C 综合 II=1 | 功能正确性 | **C 仿真 + 综合 DONE**，上板待 P3 |
| P3 | 自定义 Overlay（流式主线） | HDMI-In → 自定义算子 → HDMI-Out 实时出图 | 创新性 + 完整度 | 未开始 |
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
- **当前状态**：位流已生成（WNS +3.086 ns，LUT 7.6%、BRAM 2.5%、DSP 1.4%），`.hwh`
  已通过离线校验，上板脚本已用假 DMA 离线验证 → **只等板卡侧跑一次 DMA 回环**

#### P3b HDMI 流式 overlay（主展示形态，待采集卡/显示器）

预研结论见 `docs/p3b_plan.md`：官方 base overlay 是 4448 行、Vivado **2024.1** 生成的
tcl，带版本门禁，直接放到 2026.1 跑会被拒；`pynq.lib.video` 依赖 dvi2rgb/v_tc/v_axi4s_vid_out/
rgb2dvi/axi_dynclk 与三个 HLS IP（color_convert/pixel_pack/pixel_unpack）。两条路线与工作量
估计都写在那个文件里。

- 构建：`build/overlay_hdmi/`
- 产物：`board/hdmi_stream/`（`.bit`、`.hwh`、notebook、实测日志）
- 验收：实时出图（≥ 30 fps @ 720p），时序 WNS ≥ 0，资源报告留档

### P4 算子族 + 参数化 + UI

- 统一寄存器映射（AXI-Lite）：算子选择、参数（阈值、核权重、增益）、旁路开关、状态
- PS 侧：`src/ps/` 下 overlay 驱动封装 + ipywidgets UI
- 验收：UI 上切算子/调参，画面实时变化，无花屏无撕裂

### P5 性能与资源对比

必测五类数据（每项都要有复跑脚本与原始日志）：

| 指标 | 测法 |
| --- | --- |
| 帧率 | PL 侧帧计数寄存器 + PS 侧时间戳，双口径 |
| 延迟 | HDMI-In 打时间戳 → HDMI-Out 计数，或帧缓冲计数差 |
| 吞吐 | AXI-Stream 有效像素率（像素/秒） |
| 资源 | 综合/实现报告 LUT/FF/BRAM/DSP |
| 功耗 | 板级输入功率（外部表或无表时的估算口径，需写清测量边界） |

- 脚本：`sim/perf/` 与 `board/p5_metrics/`，输出 CSV + 自动生成对比表
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
