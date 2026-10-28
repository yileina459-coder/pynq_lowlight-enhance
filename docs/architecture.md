# 系统架构（as-built，2026-10-24）

> 本文描述**交付版本的实际结构**。早期设想（HDMI IN → 算子 → HDMI OUT 直通、四算子切换）
> 保留在 [`../report/ai_collaboration_log.md`](../report/ai_collaboration_log.md)；所有指标的口径见 [`facts.md`](facts.md)。

## 1. 两条通路

| 通路 | 数据流 | 用途 | 位流 |
| --- | --- | --- | --- |
| HDMI（主演示） | PS 预载帧 → DDR → VDMA MM2S → `stamp_in` → `enhance` → `stamp_out` → `pixel_unpack` → `sof_gen` → `v_axi4s_vid_out` → `rgb2dvi` → HDMI OUT | 640×480@60 持续出图；视觉与延迟证据 | `board/hdmi_stream_enhance/enhance_hdmi.bit` |
| DMA（数字验证） | PS ↔ DDR ↔ AXI DMA ↔ 算子（有界核） | 整帧回读，与 numpy 黄金模型逐位比对 | `board/enhance_dma/enhance_dma.bit`、`board/dma_sobel/sobel_dma.bit` |

两条通路共用 `src/hls/enhance/enhance.cpp` 同一份算法源码：DMA 版走 `ap_ctrl_hs` 有界核，
HDMI 版走 `ap_ctrl_none` 自由运行核（`enhance_body.inc` 被两个顶层函数包含）。

## 2. HDMI 通路的组成

| 模块 | 位置 | 作用 |
| --- | --- | --- |
| `enhance_stream_cfg` | `src/hls/enhance/` | 逐像素完成局部对比 → 两段色调曲线 → 二值/反色/单色 → 分屏；59 bit 配置从 BRAM 每像素读一次 |
| `cfg_bram` | `src/rtl/cfg_bram/` | XPM 真双口，两字；写侧 100 MHz（PS/GPIO），读侧 142.857 MHz（内核） |
| `sof_gen` | `src/hls/sof_gen/`（RTL 版 `src/rtl/axis_sof_gen/`） | 用「每帧 480 行 TLAST」生成 TUSER0（帧起始）；VDMA 的 TUSER 恒为 0 |
| `enh_rst_bridge` | `src/rtl/enh_rst_bridge/` | 复位异步断言 / 同步释放；BRAM 配置后切预设不再用它 |
| `axis_cycle_stamp` | `src/rtl/axis_cycle_stamp/` | 内核前后各打一次时间戳，量流水线延迟 |
| PYNQ 官方 IP | `build/overlay_hdmi_enhance/.work/` | `v_axi4s_vid_out`、`rgb2dvi`、VDMA、GPIO、HPD 控制 |

配置接口：59 bit 拆成两个字，经 AXI GPIO 写入 `cfg_bram`；切预设 = 一次寄存器写，
不复位、不中断像素流（150 s / 25 次切换 / 741 次写帧，0 次卡顿）。

## 3. 时钟与复位

- **100 MHz**：PS AXI 互联、GPIO、`cfg_bram` 写侧、状态回读。
- **142.857 MHz**：视频域（VDMA、内核、`pixel_unpack`、`v_axi4s_vid_out`、`rgb2dvi`）。
- 像素时钟 25.175 MHz（640×480@60），由 `axi_dynclk` 产生；已锁定时启动流程不再重编程
  （重编程会中断 TMDS，采集棒不一定能重新锁定）。
- 输出 HPD 必须显式驱动：AXI GPIO 上电方向寄存器全为输入，只写数据寄存器不改变引脚。
- 复位释放跨时钟域，采用异步断言 / 两级同步释放；纯组合释放会让某些预设持续闪烁。

## 4. 软件栈

**PC 侧（PowerShell / Python）**

| 入口 | 作用 |
| --- | --- |
| `上传到开发板.bat` → `tools/board/upload_panel.ps1` | 图片/视频同一个窗口；识别类型、选比例/挡位/播放方式 |
| `tools/board/show_image.ps1` | 命令行上传一张图（转码 → scp → 写控制文件 → 回读确认） |
| `tools/board/play_video.ps1` | 解码、自动选挡、上传帧序列、按 fps 推流；`-Roll` 默认保留标定值 |
| `tools/board/ensure_demo.ps1` | 检查/拉起板上常驻演示，然后自动标定偏移 |
| `tools/board/fix_offset.ps1` → `tools/board/align_output.py` | 测偏移 → 写 `/tmp/hdmi_roll.txt` → 复测残差 |
| `tools/board/reset_board.ps1`、`status.sh` | 一键恢复干净状态；一条命令看板上全部状态 |

**板上（PYNQ 3.1.1，root + venv）**

| 文件 | 作用 |
| --- | --- |
| `board/hdmi_stream_enhance/hdmi_resident.py` | 常驻演示：独占 VDMA，逐帧应用 roll/预设，读 `/tmp/hdmi_*.txt` 控制面，`fcntl.flock` 单实例 |
| `board/hdmi_stream_enhance/hdmi_live.py` | 板级封装：找 IP、写预设、开输出、拉 HPD |
| `board/enhance_dma/panel.ipynb` | DMA 通路 Jupyter 面板（8 档旧表 + 逐位比对） |
| `board/hdmi_stream_enhance/notebooks/hdmi_panel.ipynb` | HDMI 通路 Jupyter 面板（8 档旧表按钮） |

控制面是 `/tmp` 下的文本文件（`hdmi_image` / `hdmi_preset` / `hdmi_roll` / `hdmi_sof` /
`hdmi_play*`），PC 端全程不需要 sudo；进程一退出 VDMA 停供，画面回到彩条属正常现象。

## 5. 为什么不是直通

- 本板 HDMI **输出**只有 640×480 能驱动（800×600/720p/1080p 一帧都不消费，原厂 `base.bit` 同样如此）；
- HDMI **输入**又无法工作在 640×480（`dvi2rgb` 的 `kClkRange` 只接受 1/2/3）；
- 两者叠加使"输入输出同分辨率"无解，所以帧源改为 VDMA。内核仍在真实像素流上。

推导与逐条实测见 [`hdmi_status.md`](hdmi_status.md)；对交付的影响见
[`facts.md`](facts.md) 第 2 节。

## 6. 明确未实现

| 项 | 状态 |
| --- | --- |
| 三算子并行 + `axis_mux3` 切换 | 只到综合级；缺功能仿真（本机 `xsim` 启动即崩），未接入 overlay |
| 摄像头 / HDMI 直通 | 受上述硬件限制，不做 |
| HDMI 通路 `readframe()` | 不可用（VDMA 环回被切断），数字验证走 DMA 通路 |
| 端到端延迟、功耗 | 未测（直通未打通；无功率计） |
| 当前 10 档表的逐位验证 | 未做（只验过 8 档旧表） |
