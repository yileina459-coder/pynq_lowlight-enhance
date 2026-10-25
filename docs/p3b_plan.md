# P3b：把算子插进 HDMI 视频流

> **这是 2026-10-19/20 的方案与事实记录**；最终实现与当前状态见
> `board/hdmi_stream_enhance/`、[`facts.md`](facts.md)、[`hdmi_status.md`](hdmi_status.md)。

本文件记录**已经查证过**的事实和两条可选路线。没有查证的不写。

## 结论先说（已从"预研"变成"已验证"）

路线 A 走通了：PYNQ 官方 base overlay 在 **Vivado 2026.1** 里重建成功（打了 3 个补丁），
Sobel 核插在 `pixel_pack` → `pixel_unpack` 之间，视频流不经过 VDMA 帧缓冲。

| 里程碑 | 状态 | 证据 |
| --- | --- | --- |
| PYNQ 的 5 个 HLS 视频 IP 用 Vitis HLS 2026.1 重新打包 | 通过 | `build/overlay_hdmi/.work/tree/boards/ip/hls/*/solution1/` |
| base overlay 块设计在 2026.1 里生成 | 通过（4448 行 tcl，仅 3 处补丁） | `base.tcl` 日志 |
| Sobel 插入并重新连线 | 通过 | `insert_sobel.tcl` 输出 `RESULT: INSERT OK` |
| 内核在 142.86 MHz 下收敛 | 通过，估计 Fmax **194.59 MHz**、II=1 | `build/hls/sobel/reports/csynth.rpt`（7 ns 目标） |
| 位流与上板 | 见 `build/overlay_hdmi/` 与 `board/hdmi_stream/` | `sobel_hdmi.bit/.hwh` |

## 三个补丁（`build/overlay_hdmi/patch_base_tcl.py`）

| 补丁 | 原文 | 原因 |
| --- | --- | --- |
| 版本门禁 | `scripts_vivado_version 2024.1` → `2026.1` | 脚本自检不同版本会直接 `return 1` |
| IP 仓库路径 | `../../ip` → 绝对路径 | 构建目录与 PYNQ 仓库布局不同 |
| PFM_NAME | `${overlay_name}` → `base` | 2024.1 不校验；2026.1 校验并报"非法字符"（该变量在花括号里从未被替换） |

## 已查证的事实

来源：`https://github.com/Xilinx/PYNQ`，tag `v3.1.2`（PYNQ 3.1.2 镜像对应的源码）。

| 事实 | 证据 |
| --- | --- |
| PYNQ-Z2 的 base overlay 源码在 `boards/Pynq-Z2/base/` | 该目录含 `base.tcl`、`build_bitstream.tcl`、`build_ip.tcl`、`check_timing.tcl`、`vivado/constraints/base.xdc`、`base.py`、`makefile` |
| `base.tcl` 有 **4448 行**，由 Vivado 2024.1 生成 | 文件头 `set scripts_vivado_version 2024.1`，并有一段版本检查：非 2024.1 时打印 ERROR 并 `return 1`，脚本直接中止 |
| 视频通路用到的 IP | `digilentinc.com:ip:dvi2rgb:1.7`（HDMI 输入）、`digilentinc.com:ip:rgb2dvi:1.2`（HDMI 输出）、`digilentinc.com:ip:axi_dynclk:1.0`（像素时钟）、`xilinx.com:ip:v_vid_in_axi4s:5.0`、`xilinx.com:ip:v_axi4s_vid_out:4.0`、`xilinx.com:ip:v_tc:6.2`（时序控制器）、`xilinx.com:user:color_swap:1.1` |
| 像素格式转换是 HLS IP | `xilinx.com:hls:color_convert:1.0`、`pixel_pack:1.0`、`pixel_unpack:1.0`，源码在 `boards/ip/hls/`，由 `build_ip.tcl` 用 `vitis_hls` 重新打包 |
| IP 仓库路径 | `base.tcl` 里 `set_property ip_repo_paths ../../ip`，即 `boards/ip` |
| base overlay 还含 MicroBlaze、TIMER、SPI、IIC、音频、Arduino/Pmod 等与本项目无关的部分 | `base.tcl` 中的 `lmb_v10`、`lmb_bram_if_cntlr`、`axi_timer`、`axi_quad_spi`、`axi_iic` 等实例 |
| 视频端口在 `video` 层次下 | `get_bd_intf_pins -hier -filter {NAME =~ "*stream*"}` 得到 `/video/hdmi_in/out_stream`、`/video/hdmi_out/in_stream` |
| 视频逻辑时钟是 `clk_142M`（PS 的 FCLK_CLK1） | 插入脚本把内核 `ap_clk` 接到 `video/clk_142M` 所在网络，网络名 `ps7_0_FCLK_CLK1` |
| `pixel_pack` 输出是 **32 位**/像素 | 因此 Sobel 核用 `SOBEL_PIX_W=32` 直接对接，**不需要位宽转换** |

## 两条路线

### 路线 A：移植官方 base overlay（保 PYNQ 视频 API）

保留 PYNQ `pynq.lib.video` 的 `hdmi_in` / `hdmi_out` API，把 Sobel 插在
`pixel_pack` 之后、`pixel_unpack` 之前。

- 优点：PS 侧代码几乎不用写，`configure()`/`tie()`/`readframe()` 都是现成的；
  评分里"使用 PYNQ 框架"的叙事也最完整。
- 代价：要在 2026.1 里把 4448 行的 2024.1 脚本跑通，涉及版本门禁、IP 升级、
  MicroBlaze 子系统；HLS IP 需要重新打包（或用仓库里现成的 zip）。
- 工作量估计：2~4 个工作日（含排错）。

### 路线 B：自己搭最小视频通路（不用 PYNQ 视频库）

自己用 `v_tc` 产生时序、AXI-Lite 寄存器配置分辨率和时钟，PS 侧写一个最小驱动。

- 优点：只用 8~10 个 IP，结构可控，时序问题容易定位。
- 代价：PS 侧要自己写视频时序配置与颜色格式处理，**这部分恰好是 PYNQ 视频库帮你做掉的**；
  对一个零基础的队伍来说，这条路的学习成本比 A 高，且失败时没有参照物。
- 工作量估计：3~5 个工作日。

**建议**：先试路线 A 的第一步——只做"2026.1 原样重建 base overlay"，不改任何结构。
如果这一步能在半天内跑通，剩下的"插一个 IP"就不难；如果跑不通（IP 升级连环报错），
再评估路线 B 或换用 2025.2 工具链（赛规允许，需在报告中说明）。

**这个建议已被验证**：路线 A 从零到出位流只用了 3 个补丁，没有遇到 IP 版本不兼容，
不需要 `upgrade_ip`，也不需要退回 2025.2。路线 B 不再考虑。

## 路线 A 的实际步骤（已实现于 `build/overlay_hdmi/`）

1. `fetch_pynq.ps1`：按 v3.1.2 稀疏克隆 PYNQ，取出 `boards/Pynq-Z2` 与 `boards/ip`，
   放进 `.work/tree/`（不上传第三方源码进仓库，构建时拉取，版本可复现）；
2. `patch_base_tcl.py`：三个补丁（见上表），每个补丁都校验原文存在，改不到就报错退出；
3. `build_ip.tcl`：用 Vitis HLS 2026.1 重新打包 5 个 HLS IP
   （color_convert / pixel_pack / pixel_unpack / trace_cntrl_32 / trace_cntrl_64）；
4. `base.tcl`：生成 4448 行的块设计；
5. `insert_sobel.tcl`：切断 VDMA 环回，把 `video/hdmi_in/out_stream` 接到 `sobel_0`，
   再接到 `video/hdmi_out/in_stream`；时钟/复位复用 `video/clk_142M` 所在网络；
6. `build_bitstream.tcl`：加 wrapper、约束、实现、写位流，导出 `base.bit` / `base.hwh`；
7. `build.bat` 把产物改名为 `board/hdmi_stream/sobel_hdmi.bit|.hwh`。

## 风险与对策

| 风险 | 影响 | 对策 |
| --- | --- | --- |
| 2024.1 生成的 tcl 在 2026.1 里 IP 版本不兼容 | 块设计建不起来 | 实测未发生；如遇到则逐 IP `upgrade_ip`，或改用 2025.2（赛规允许） |
| PYNQ 镜像版本与 overlay 不匹配 | hwh 解析失败 | 上板脚本会明确报 `no 'video' hierarchy`；届时按实际版本改 `fetch_pynq.ps1 -Tag` 重建 |
| 没有显示器，无法验证 HDMI 输出 | 只能靠采集卡 | 采集卡（几十元）或借一台显示器；数字证据由 DMA 版提供 |
| VDMA 被断开，`readframe()` 不可用 | PS 不能回读帧 | 这是低延迟直通的取舍，已写入 `board/hdmi_stream/README.md` |

## 当前状态：位流已生成

- `board/hdmi_stream/sobel_hdmi.bit` / `.hwh` 已构建：**WNS +0.207 ns**（142.857 MHz 视频时钟，0 个失败端点）；
- 资源：LUT 62.2%、FF 43.8%、BRAM 57.5%、DSP 9.6%（base overlay 的 MicroBlaze/音频/IO 子系统占大头，Sobel 核本身约 1%）；
- `.hwh` 通过 `skill/overlay_check`：188 个模块、`sobel_0` 在位、`ap_clk` 报告为 142.857 MHz；
- 剩余：板上加载验证（`board/hdmi_stream/hdmi_sobel.py`），需显示器或采集卡看输出画面。
