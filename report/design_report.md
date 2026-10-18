# 设计报告：基于 PYNQ-Z2 的 HDMI 实时视频处理流水线

> 参赛方向：2026 全国大学生嵌入式芯片与系统设计竞赛 · FPGA 创新设计赛道 · AMD 自主选题赛道（初级组）
> 器件：Zynq-7000 XC7Z020（PYNQ-Z2）　工具：Vivado / Vitis HLS 2026.1
> 本报告中的所有数字都来自仓库内的脚本与日志，路径随文给出，可逐条复核。

## 1. 选题背景与创新点

### 1.1 要解决的问题

视频处理算法的硬件加速常被当作"把算子写进 FPGA 就快了"，但真正决定作品价值的三个问题是：
**结果对不对、比软件快多少、别人能不能复现**。本项目围绕这三点组织：

- 每个算子都有**独立的软件黄金模型**，硬件输出与之做 **0 容差逐像素比对**；
- 同一算法同时给出 **PS 纯软件实现**与 **PL 硬件实现**，用同一套输入、同一套测量脚本对比；
- 全部流程脚本化（HLS 工程、块设计、位流、上板测试），一条命令可从零重建。

### 1.2 创新点

| 创新点 | 具体做法 | 为什么有价值 |
| --- | --- | --- |
| 流式算子内核 | 行缓冲 + 3 抽头移位寄存器，II=1，`ap_ctrl_none`，无 AXI-Lite 依赖即可插在视频流中间 | 延迟约一行，而不是一帧；可直接嵌入 HDMI 通路 |
| 边界策略显式化 | 水平复制、垂直用上一帧行，写进头文件注释、测试台与 Python 参考 | 这是"硬件和软件对不上"的头号原因，显式定义后可以要求 0 误差 |
| 双路验证 | DMA 版（可回读、可数字验证）+ HDMI 版（实时展示）共用同一内核 | 没有显示器也能证明硬件正确；有显示器时又能实时演示 |
| 可复用工具链 | 三个通用 PYNQ Skill（overlay 离线校验、逐位比对、性能数据入库） | 换题目、换板卡仍可用，符合赛题"通用 PYNQ Skill"加分项 |

## 2. 设计原理与功能框图

### 2.1 系统框图

```text
                 ┌──────────────────────────── PYNQ-Z2 (XC7Z020) ───────────────────────────┐
 HDMI 源 ──────► │ HDMI IN ─ dvi2rgb ─ v_vid_in_axi4s ─ color_convert ─ pixel_pack ─┐        │
                 │                                                                  │        │
                 │                            ┌─────────────────────────────────────┴──┐    │
                 │                            │  sobel_0 / gaussian_0 / sharpen_0（HLS 算子，AXI-Stream）│    │
                 │                            └─────────────────────────────────────┬──┘    │
                 │                                                                  │        │
 HDMI 显示器 ◄── │ HDMI OUT ─ rgb2dvi ─ v_axi4s_vid_out ─ color_convert ─ pixel_unpack ┘        │
                 │                                                                           │
                 │  PS (ARM Cortex-A9)：Jupyter / Python ── AXI-Lite ── 配置与状态           │
                 └───────────────────────────────────────────────────────────────────────────┘
```

两条数据通路共用同一个算子 IP：

| 通路 | 结构 | 用途 |
| --- | --- | --- |
| DMA 版 | PS ↔ DDR ↔ AXI DMA ↔ 算子 | 数字验证（与黄金参考逐位比对）、便于自动化测试 |
| HDMI 版 | HDMI IN ↔ 算子 ↔ HDMI OUT，绕过 VDMA 帧缓冲 | 实时展示，延迟约一行 |

### 2.2 算子内核结构（以 Sobel 为例）

```text
 像素流 ──► 亮度 Y=(77R+150G+29B)>>8 ──► 行缓冲×3（轮转）
                                              │
                          ┌───────────────────┴───────────────────┐
                          │  每行 3 抽头移位寄存器 → 3×3 窗口        │
                          │  Gx = 右列 − 左列,  Gy = 下行 − 上行      │
                          │  M  = |Gx| + |Gy|，饱和到 0..255         │
                          └───────────────────┬───────────────────┘
                                              ▼
                                     {M,M,M} 复制到 RGB
```

关键设计决策：

1. **三个行缓冲轮转 + 每行移位寄存器**，使每个像素对每个行缓冲只做 1 次读、1 次写，
   正好落在真双口 BRAM 的能力内，这是 II=1 能成立的原因；
2. **整数亮度与整数梯度**，不使用浮点，保证硬件与软件参考**逐位一致**；
3. **`ap_ctrl_none`**：无 start/done 握手，数据到即处理，适合插在视频流中间；
   行边界由 `TLAST` 识别，因此不需要在运行时配置分辨率。

## 3. 软硬件划分依据与接口设计

### 3.1 划分依据

| 功能 | 放在 | 理由 |
| --- | --- | --- |
| 视频时序、颜色空间转换、像素打包 | PL（PYNQ 官方 IP） | 需要与像素时钟严格同步 |
| 卷积算子 | PL（自研 HLS） | 每像素固定算术，适合流水；PS 上逐像素循环慢两个数量级 |
| 参数配置、状态监控、UI | PS（Python/Jupyter） | 变化慢、需要交互，放软件更灵活 |
| 黄金参考与比对 | PS / 主机 | 需要浮点与丰富库，且要独立于硬件实现 |

### 3.2 接口定义

**算子 IP（AXI4-Stream）**

| 端口 | 位宽 | 语义 |
| --- | --- | --- |
| `s_in_tdata` | 32 | 低 24 位为 `{R,G,B}`，高 8 位透传（alpha/控制） |
| `s_in_tlast` | 1 | 行尾 |
| `s_in_tkeep/tstrb/tuser/tid/tdest` | — | 原样透传 |
| `s_out_*` | 同上 | 每输入一拍输出一拍 |
| `ap_clk` / `ap_rst_n` | — | 与视频通路同域（`clk_142M`） |

**DMA 版寄存器**：仅 AXI DMA 自身寄存器（`0x41E00000–0x41E0FFFF`），算子无 AXI-Lite。

## 4. 优化过程与前后对比

### 4.1 已完成的三次优化

| 轮次 | 问题 | 措施 | 结果 |
| --- | --- | --- | --- |
| 1 | 24 位像素流无法直接接 AXI DMA（DMA 只搬 32 位字，4:3 位宽转换不可实现） | 把像素位宽做成 `SOBEL_PIX_W` 宏，核只取低 24 位、其余透传 | 同一份源码同时服务 DMA（32）与 HDMI（24）两条通路 |
| 2 | 10 ns 约束下估计 Fmax 141.9 MHz，低于视频通路 142.86 MHz | 把约束改为 7 ns 重新综合 | 估计 Fmax **194.59 MHz**，II 仍为 1 |
| 3 | 高斯核"先行后列"两遍实现导致中间结果被 8 位字段截断 | 改为一次 9 抽头求和、12 位累加器，最后统一 `>>4` | C 仿真从 FAIL 变为 0 误差 |

### 4.2 资源与时序（HLS 综合，`xc7z020clg400-1`，7 ns）

| 算子 | BRAM | DSP | FF | LUT | II | 估计 Fmax |
| --- | --- | --- | --- | --- | --- | --- |
| Sobel | 3（1%） | 2 | 583 | 809（1%） | 1 | 194.59 MHz |
| Gaussian | 9（3%） | 0 | 1021 | 986（1%） | 1 | 194.59 MHz |

完整实现（DMA overlay，100 MHz）：LUT 4027（7.6%）、FF 5645（5.3%）、BRAM 3.5（2.5%）、DSP 3（1.4%），
**WNS +3.086 ns**（`build/overlay_dma/out/timing_impl.rpt`）。

完整实现（HDMI overlay = PYNQ base overlay + Sobel，142.857 MHz）：LUT 33098（62.2%）、FF 46563（43.8%）、BRAM 80.5（57.5%）、DSP 21（9.6%），**WNS +0.207 ns**、0 个失败端点（`board/hdmi_stream/timing_impl.rpt`）。资源占用主要来自 base overlay 的 MicroBlaze、音频、Arduino/Pmod/树莓派 IO 子系统，自研 Sobel 核本身只占约 1%——这组数字说明“把算子插进现成框架”的代价主要在框架，而不在算子。

### 4.3 PS 与 PL 对比（待板上实测补齐）

对比脚本已就位（`sim/perf/make_comparison.py`），数据由 `board/ps_baseline/ps_sobel.py`
与 `board/dma_sobel/sobel_dma.py` 写入同一个 `metrics.csv`。
主机侧参考值：numpy 1280×720 约 **40.7 ms/帧**（24.6 fps）；板上 ARM 实测值待补。

## 5. 功能正确性验证

| 验证项 | 方法 | 结果 |
| --- | --- | --- |
| Sobel 逻辑 | C 仿真 + 独立软件黄金模型，推 3 帧，比较第 3 帧 | 9216 拍，**0 误差**，侧带信号完好 |
| Gaussian 逻辑 | 同上 | 9216 拍，**0 误差** |
| 边界策略 | 水平复制 / 垂直上一帧行，测试台与 Python 参考同口径 | 逐位一致 |
| 硬件通路 | DMA 回环 + 与 `data/reference/sobel_720p.png` 比对 | 脚本与离线假 DMA 已验证，板上待执行 |
| Overlay 结构 | `.hwh` 离线校验（IP 清单、地址、时钟频率） | 6 个 IP、9 个时钟，PASS |

## 6. 大模型协作记录

完整交互记录见 [`report/ai_collaboration_log.md`](ai_collaboration_log.md)，包含提示词、产出、
**每一次错误的诊断与纠正**（截至当前 15 条），以及哪些决定是队员拍板的。几条典型：

- PDF 解析：`bfrange` 数组形式与 `/Lang` 属性导致乱码，两轮定位；
- `export_design` 缺 `XILINX_VIVADO`；HLS 启动器缺失；ap_int 三元表达式位宽歧义；
- PowerShell 重定向把 UTF-8 写成 UTF-16；`Set-Content` 写的 tcl 带 BOM 导致 Vivado 解析失败；
- `git sparse-checkout` 在仓库子目录执行，把整个工作区设成稀疏检出（最危险的一次，已记录恢复方法）；
- PYNQ base overlay 的 3 个移植补丁，以及 `-jobs 4` 并发引发的 Tcl app store 竞争。

## 7. 技能包提炼过程

三个 Skill 都来自"实际踩过的坑"，而不是凭空设计：

| Skill | 从什么失败中提炼 | 已验证效果 |
| --- | --- | --- |
| `skill/overlay_check` | 位流/`.hwh` 不配套、IP 没接时钟，上板才发现 | 对真实 `.hwh` PASS（6 IP / 9 时钟），缺 `.bit` 时正确 FAIL |
| `skill/golden_compare` | "看着差不多"掩盖了边界策略不一致 | PASS / FAIL / 容差三种情形均验证；报出首个差异像素坐标 |
| `skill/perf_collect` | 手抄性能数字无法复核 | 记录→汇总→生成报告表格全链路验证 |

每个 Skill 的 README 都写了**适用范围 / 使用方法 / 失效条件 / 已验证效果**四段。

## 8. 复现说明

```powershell
# 0) 环境：Vivado / Vitis HLS 2026.1，许可与坑位见 docs/env.md
# 1) 工具链冒烟（各约 1 分钟）
cd build\smoke\vivado ; ..\..\..\tools\env\vivado.bat -mode batch -source synth_smoke.tcl
cd build\smoke\hls    ; ..\..\..\tools\env\vitis_hls.bat -f run_hls.tcl

# 2) HLS 算子（C 仿真 + 综合 + 导出 IP）
tools\env\vitis_hls.bat -f build\hls\sobel\run_hls.tcl
tools\env\vitis_hls.bat -f build\hls\gaussian\run_hls.tcl

# 3) DMA overlay 位流
build\overlay_dma\build.bat

# 4) HDMI overlay 位流（拉取 PYNQ v3.1.2 源码并打补丁）
build\overlay_hdmi\build.bat

# 5) 上板
#    板上：python3 sobel_dma.py            （DMA 版，逐位比对）
#          python3 hdmi_sobel.py --seconds 10  （HDMI 版，需显示/采集）
```

## 9. 尚未完成与已知限制

- 板上实测数据（帧率、延迟、资源、功耗）待采集，`metrics.csv` 与对比表将据此生成；
- HDMI 版绕过 VDMA，因此 PS 侧不能 `readframe()`（取舍已文档化）；
- DMA 版按行传输，帧率受 Python 每次传输开销拖累，仅用于功能验证；
- 算子族：Sobel、Gaussian、Sharpen 已完成并验证；色彩空间转换按设计复用 PYNQ 官方 color_convert IP，不自研；
- 功耗尚无板级测量手段，报告中将明确标注测量边界。
