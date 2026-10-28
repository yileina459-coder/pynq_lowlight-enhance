# 事实基线（2026-10-25 整理，测量截至 2026-10-24）

> **本页是全仓库唯一的数字口径。** README、设计报告、海报、PPT 里出现的
> 指标都应当与本页一致；不一致时以本页和它列出的证据文件为准，改文档而不是改数字。
>
> 时间线文档（[`hdmi_status.md`](hdmi_status.md)、[`../report/ai_collaboration_log.md`](../report/ai_collaboration_log.md)）
> 保留当时的原文，只在文首/文末加"后续更正"指针，不回头改写记录。
>
> 平台：PYNQ-Z2（Zynq-7000 XC7Z020）　工具：Vivado / Vitis HLS 2026.1　镜像：PYNQ 3.1.1

## 1. 交付位流

| 项 | 值 | 证据 |
| --- | --- | --- |
| 文件 | `board/hdmi_stream_enhance/enhance_hdmi.bit` / `.hwh` | 仓库内文件 |
| MD5 | `c9a27af6c17cb31954d8ed0fd19acdb0` | `evidence/final_measurements.json` |
| 内容 | HLS `sof_gen`（`/video/hdmi_out` 内）+ `enhance_stream_cfg` 内核（`b36925a`） | `evidence/final_measurements.json` |
| 时序 | **WNS +0.206 ns @142.857 MHz**，0 失败端点 | [`timing_impl.rpt`](../board/hdmi_stream_enhance/timing_impl.rpt) |
| 流水线深度 | **21 拍 = 147 ns**（HLS `Depth = 21`） | HLS 综合报告、`timing_impl.rpt` |
| 片上时间戳 | 21–25 拍（只锁存首拍，含启动偏斜；同一轮内恒定） | `axis_cycle_stamp`、[`hdmi_status.md`](hdmi_status.md) |
| 资源（HLS 估计） | BRAM 3（1%）/ DSP 2 / FF 2168（2%）/ LUT 1659（3%），II=1，估计 Fmax **194.59 MHz**（5.139 ns @7 ns 约束） | `build/hls/enhance/…/csynth.rpt` |

历史版本（+0.289 / +0.354 / +0.171）都是构建过程中的中间构建，**不是交付位流**；
`board/hdmi_stream_enhance/README.md` 里这些旧值是时间线记录。

## 2. 分辨率与数据通路

- 输出：**640×480 @60**（像素时钟 25.175 MHz）。这是这块 PYNQ-Z2 的**物理上限**：
  800×600 / 720p / 1080p 下 VDMA 一帧都不消费、不产生 TMDS，**原厂 `base.bit` 同样如此**。
- 输入：HDMI 输入**无法工作在 640×480**（`dvi2rgb` 的 `kClkRange` 只接受 1/2/3，25.175 MHz 需要 5 档）。
- 因此 **HDMI 直通（摄像头/笔记本 → 板子 → 显示器）没有打通**，也不再作为交付路径。
- 交付形态：**PS 预载图像/视频帧 → DDR → VDMA MM2S → `stamp_in` → `enhance` → `stamp_out`
  → `pixel_unpack` → `v_axi4s_vid_out` → `rgb2dvi` → HDMI OUT**。内核在真实像素流上，PS 只送帧、改配置。
- 帧源不是摄像头：图像与视频都由上传工具在 PC 侧准备好，传到板上由常驻进程推流。

## 3. 增强链与参数

- 一颗 AXI-Stream 流式内核，逐像素完成：局部对比（`clarity`）→ 两段色调曲线（`knee` + `gain_lo`/`gain_hi`）
  → 二值/反色/单色（`thresh`/`binarize`/`invert`/`mono`）→ 左右分屏（`split_x`）。
- 参数共 **59 bit**，经 AXI GPIO 写入、存放在 `cfg_bram`（XPM 真双口），内核**每像素读一次**；
  切预设 = 一次寄存器写，**不复位、不中断像素流**。
- 运行期切换实测：**150 s / 25 次切换 / 741 次写帧，0 次 >60 ms 的卡顿**，延迟全程 21 拍。

## 4. 预设：两套表，别混

| 用途 | 档数 | 档名 | 验证状态 |
| --- | --- | --- | --- |
| 当前常驻演示 / 上传 / 视频选挡（`hdmi_live.py`、`preview_enhance.py`） | **10** | pass, clarity, crisp, bright, night, document, reading, invert, binarize, split | 运行期切换已验证；**未做逐位比对** |
| DMA 逐位验证 + Jupyter 面板（`board/enhance_dma/`、`panel.ipynb`） | **8** | pass, clarity, reading, document, night, invert, binarize, split | **各 0/2,764,800 通道不一致**（720p，15.6 ms/帧） |

两张表的 `night` / `document` 参数并不相同（`metrics_enhance.csv` 记的是旧表），
所以只能写「8 档（DMA 验证用的那张参数表）逐位一致」，**不能**写成「10 档逐位一致」。
`tools/check_presets.py` 只校验 `hdmi_live.py` 与 `preview_enhance.py` 两张表一致（10 档），
不覆盖面板的旧表——这是已知差异。

## 5. 输出画面偏移

**结论：相位是「这一路像素流」的属性，不是画面的属性，也不是每帧重掷的。**

- 同一路流内：换图、换挡位、常驻进程每 200 ms 重推，读数都不变（±1 px）。
- 只有像素流重新启动（常驻进程重启 / 板子重启）才会变。
- 2026-10-24 实测：`roll=0` 时 **W = 216.8 源像素**；写 `roll=218` 后行首对齐，残差 **0–1 px**
  （真实书页与推送 PNG 的归一化互相关峰值 `dx=0, dy≈−1`）。
- 机制：`v_axi4s_vid_out` 用 TUSER0（SOF）对齐帧；VDMA 的 TUSER 恒为 0，板上用 `sof_gen`
  按「每帧 480 行 TLAST」生成 SOF。计数器从复位开始数，所以**第一个帧边界 = 流启动后遇到的
  第一条 480 行边界**，相位因此落在亚行范围内、并随启动时刻变化。
- 历史读数 0 / 45 / 89 / 0.3 px 都来自**别的像素流**（不同次启动），不是"同一路流里随机"；
  早期"每帧随机相位"的结论已确认是**测量缺陷**（截图抓错了 OBS 窗口）。
- 修法：启动后测一次、写补偿、复测残差——`tools\board\fix_offset.ps1`（或双击根目录
  **调整画面偏移.bat**），`ensure_demo.ps1` 拉起演示后自动调用。
- 视频上传不再清零标定：`play_video.ps1` 的 `-Roll` 默认 `-1` = 保留板上已有值。
- 位流层面的根治（真实帧边界 SOF / 接出 VDMA 的 TUSER）仍需重建位流，本次未做。

## 6. 性能

| 指标 | 值 | 口径 |
| --- | --- | --- |
| enhance 整帧（720p，AXI-DMA） | **15.6 ms/帧 = 63 fps** | `board/enhance_dma/metrics_enhance.csv` |
| enhance 流水线延迟 | **16 拍 = 160 ns @100 MHz** | DMA 通路双时间戳 |
| HDMI 通路延迟 | **21 拍 = 147 ns @142.857 MHz** | HLS Depth + 片上时间戳 |
| Sobel PS（ARM + numpy） | **3108.4 ms/帧**（0.32 fps） | `board/dma_sobel/metrics_board.csv` |
| Sobel PL 整帧 | **15.8 ms/帧**（63.45 fps），**196.7×** | 同上、[`comparison.md`](../report/comparison.md) |
| Sobel PL 逐行（对照） | 659.1 ms/帧（4.72×） | 刻意保留的对照配置 |
| 720p60 一行时间 | 17.2 µs；160 ns ≈ 1% 行 | 换算 |

**归属**：196.7× 是 **Sobel** 的 PS vs PL 数据；enhance 自己的板上数据是 15.6 ms/帧 + 逐位一致。
**不要**把 196.7× 写成 enhance 的加速比。

## 7. 稳定性与演示

- 单实例（`hdmi_resident.py` 用 `fcntl.flock`）连续运行 **15 分钟，0 次 `writeframe` 失败**。
- 启动流程：`tools\board\ensure_demo.ps1`（没跑就拉起，然后自动标定偏移）。
- 日常操作：双击 **上传到开发板.bat**（图/视频同一个窗口）；`tools\board\status.sh` 看板上状态；
  `tools\board\reset_board.ps1` 一键恢复干净状态。
- 采集卡丢锁后不能自恢复：像素流中断只能拔插 HDMI 线或重启板子，所以**演示只启动一次**。
- 进程退出后画面回到彩条是正常现象（VDMA 停供），不是故障。

## 8. 指标边界

| 项 | 状态 |
| --- | --- |
| 端到端延迟（采集→显示） | **未覆盖**（本版本只测 PL 内部延迟） |
| 功耗 | **未测**（PYNQ-Z2 无板载功率计，报告里没有估算值） |
| 三算子并行 + `axis_mux3` | 只到综合级；`axis_mux3` 缺功能仿真（本机 `xsim` 启动即崩） |
| 当前 10 档参数表的逐位验证 | 8 档已验证；`crisp`、`bright` 两档只做运行期验证 |
| HDMI 直通 / 摄像头输入 | 受硬件限制，不做 |
| `readframe()` 取 HDMI 通路帧 | 不可用（VDMA 环回被切断），数字验证走 DMA 通路 |

## 9. 数字口径

1. **不写"实时"** 来表示"摄像头进 → 屏幕出"：本版本的帧源由主机上传。可写的事实：内核在真实像素流上、
   HDMI 通路 640×480@60 持续出图、DMA 通路 720p 15.6 ms（63 fps）。
2. **延迟**写「片上流水线延迟 16 个像素时钟 = 160 ns」（DMA）或「21 拍 = 147 ns」（HDMI），
   两个数都对但别混用；**不写「端到端 160 ns」**——端到端没测。
3. **196.7× 属于 Sobel**，不是 enhance 的加速比。
4. **8 档 vs 10 档**：写「10 档预设可切换」和「8 档（DMA 参数表）逐位一致」都成立，
   不要混成「10 档逐位一致」。
5. **功耗不写数字**，任何功耗值都是编的。
6. **HDMI 只能 640×480**，不要写 720p / 1080p 输出；DMA 通路的 15.6 ms 是 720p 回环进 DDR，
   不是 HDMI 输出分辨率。
7. **偏移**写「每次演示启动后标定一次，本次 218，残差 0–1 px」；不写「0.3 px 已消除」。
8. 字面计数（提交表单）按「字符数（不含空格，含标点与英文数字）」统计。

## 10. 证据索引

| 想证明什么 | 看哪里 |
| --- | --- |
| 交付位流与时序 | `board/hdmi_stream_enhance/timing_impl.rpt`、`evidence/final_measurements.json` |
| 板上逐位一致 | `board/enhance_dma/metrics_enhance.csv`、`board/dma_sobel/metrics_board.csv` |
| 偏移测量与修法 | [`output_offset.md`](output_offset.md)、`board/hdmi_stream_enhance/evidence/offset_before_after.png` |
| HDMI 为什么只能 640×480 | [`hdmi_status.md`](hdmi_status.md)（2026-10-22 各节） |
| 视频播放与自动选挡 | [`video_playback.md`](video_playback.md) |
| 上传与提亮 | [`image_upload.md`](image_upload.md) |
| 设计叙述与优化过程 | [`../report/design_report.md`](../report/design_report.md) |
| 纠错时间线（55 条） | [`../report/ai_collaboration_log.md`](../report/ai_collaboration_log.md) |
