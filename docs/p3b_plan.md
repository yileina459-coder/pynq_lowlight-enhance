# P3b 预研：把算子插进 HDMI 视频流

本文件记录**已经查证过**的事实和两条可选路线。没有查证的不写。

## 结论先说

P3b 不是"改几行 tcl"就能完成的：PYNQ 的视频子系统（`pynq.lib.video`）依赖一整套
IP 和固定的层次结构，而官方 base overlay 的构建脚本是 **Vivado 2024.1 生成**的，
直接拿到 2026.1 里跑会被版本检查拦住。所以这一步要单独安排一轮，并且有明确的降级方案。

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

## 路线 A 的具体步骤（待执行）

1. 把 `boards/Pynq-Z2/base/` 与 `boards/ip/` 引入仓库 `third_party/pynq/`，附 BSD-3 许可说明；
2. 创建 `build/overlay_hdmi/`，用脚本复制并打补丁：
   - 把 `scripts_vivado_version` 改成 `2026.1`（或直接去掉版本门禁）；
   - `set_property ip_repo_paths` 指向仓库内的 `third_party/pynq/ip`；
3. 先跑 `build_ip.tcl`（HLS 三个 IP：color_convert / pixel_pack / pixel_unpack），
   失败就逐个人工用 `vitis_hls` 编译并检查时序；
4. 跑 `base.tcl` 建块设计，遇到 IP 版本不认识就用 `upgrade_ip` 升级并检查连线；
5. `validate_bd_design` 通过后，插入 `sobel_0`（24-bit 版本，`SOBEL_PIX_W=24`）：
   `pixel_pack → sobel_0 → pixel_unpack`，TLAST/TUSER 语义由 PYNQ 的 pack/unpack 保证；
6. `build_bitstream.tcl` 出位流，导出 `.bit` + `.hwh`；
7. 上板：`hdmi_in.configure()` → `hdmi_out.configure(mode)` → `tie()`，确认画面是边缘图。

## 风险与对策

| 风险 | 影响 | 对策 |
| --- | --- | --- |
| 2024.1 生成的 tcl 在 2026.1 里 IP 版本不兼容 | 块设计建不起来 | 逐 IP `upgrade_ip`；仍有问题则改用 2025.2（赛规允许） |
| 重打包 HLS IP 时 2026.1 的接口变化 | `color_convert` 等 IP 接口与 tcl 不匹配 | 优先使用仓库里已打包的 zip（`boards/ip/hls/*/solution1/impl/ip/*.zip`） |
| PYNQ 镜像版本与 overlay 不匹配 | hwh 解析失败 | 需要板子上 `pynq.__version__` 的实测值（**待用户提供**） |
| 没有显示器，无法验证 HDMI 输出 | 只能靠采集卡 | 采集卡（几十元）或临时借一台显示器 |

## 当前状态

- 源码已拉取并核对（`v3.1.2` 的 `boards/Pynq-Z2/base`、`boards/ip`）；
- **未开始移植**：等用户确认 PYNQ 镜像版本与是否有显示/采集设备后，再决定走 A 还是 B。
