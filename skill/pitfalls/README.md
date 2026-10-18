# pitfalls — 踩坑清单（PYNQ / Vivado / Vitis HLS）

## 适用范围

任何在 **Windows + Vivado/Vitis HLS 2024.x~2026.x + PYNQ** 上做自定义 overlay 的项目。
每一条都是本项目真实遇到过的，不是从论坛抄的推测。按"现象 → 触发条件 → 定位方法 → 修复"组织，
排查时可以直接按现象检索。

## 1. 工具链与许可

| 现象 | 触发条件 | 定位方法 | 修复 |
| --- | --- | --- | --- |
| `The vitis_hls executable is deprecated` 但仍能用 | 2026.1 起 HLS 并入 Vitis | 只是 WARNING | 可忽略；长期迁移到 `vitis-run --mode hls --tcl` |
| `vitis_hls` 不是内部或外部命令 | 安装目录只有 `bin/unwrapped/win64.o/vitis_hls.exe`，没有 `vitis_hls.bat` | `dir /s vitis_hls*` | 用包装脚本自己 call `loader.bat -exec vitis_hls`（见 `tools/env/vitis_hls.bat`） |
| 直接跑 `vitis_hls.exe` 报 `RDI_DATADIR is not set` | 绕过启动器 | 报错原文 | 必须走 loader，不要直接调 exe |
| `export_design` 报 `Cannot find Vivado, please check XILINX_VIVADO` | 只 call 了 Vitis 的 settings | 环境变量 `XILINX_VIVADO` 为空 | 先 call Vivado 的 `.settings64-Vivado.bat` |
| 综合/实现报 `Failed to create directory 'C'`、`Could not open 'C' for writing` | 多个 OOC 综合进程并发写 `%APPDATA%\Xilinx\...\XilinxTclStore` | 日志里 `tclapp::load_apps` | 删掉 `.tcl_store_lock`，并把 `launch_runs` 的 `-jobs` 降到 1 |

## 2. Tcl / 脚本

| 现象 | 触发条件 | 定位方法 | 修复 |
| --- | --- | --- | --- |
| `invalid command name "﻿open_project"` | 用 PowerShell `Set-Content -Encoding UTF8` 生成的 tcl 带 BOM | 看报错命令名前面那个不可见字符 | tcl 一律用不带 BOM 的方式写（本仓库用编辑工具直写） |
| 中文变乱码、行粘连 | `Get-Content -Raw` 读 UTF-8 后用 `Set-Content` 回写（默认 ANSI） | `git diff` 看整文件都变了 | 文本处理用 Python 且显式 `encoding='utf-8'` |
| `No projects are currently open` | 在 `open_project` 之前调 `get_property ... [current_project]` | 报错栈 | 先开工程，再设置 IP 仓库 |
| 自定义参数取到 `-f` | `vitis_hls -f x.tcl 7` 时 `$argv` 含 `-f` 与脚本名 | `puts $argv` | 遍历 `$argv` 找第一个整数 |
| `PFM_NAME name '${overlay_name}' is not valid` | 2026.1 校验 PFM_NAME；旧版生成脚本里变量在花括号中从未替换 | 报错原文 | 改成字面量 |

## 3. HLS 算子

| 现象 | 触发条件 | 定位方法 | 修复 |
| --- | --- | --- | --- |
| `conditional expression is ambiguous; ap_int<17> can be converted to ap_int<16>` | `gx < 0 ? -gx : gx`（取负会加 1 位） | 编译报错 | 先算同宽临时量 `neg_gx` 再选择 |
| 仿真结果"看着对"但逐位比对差很多 | 中间结果位宽不足，被 8 位字段截断（如 `4*255=1020` 存不进 8 位） | 逐位比对 + 打印首个差异像素 | 用足够宽的累加器（12 位）一次算完再归一化 |
| 锐化后亮边变黑边 | 负值直接赋给无符号变量（回绕） | 看直方图/极值 | `ap_int<12>` + 显式钳位，并与软件 `np.clip` 对齐 |
| II 达不到 1 | 行缓冲每周期被读多次 | `csynth` 报告里的 II 与资源 | 每行加 3 抽头移位寄存器，使每个行缓冲每周期只读 1 次 |
| Fmax 差一点点不收敛 | 约束给的目标不是实际时钟（如按 100 MHz 综合、实际跑 142.86 MHz） | 对比 `create_clock` 与实际时钟 | 直接按最严时钟综合（本项目 7 ns），一份 IP 覆盖两条通路 |

## 4. Vivado 块设计

| 现象 | 触发条件 | 定位方法 | 修复 |
| --- | --- | --- | --- |
| `Parameter does not exist: c_m_axis_s2mm_tdata_width` | AXI DMA 的 S2MM 流位宽参数名不同 | `list_property` 打印 IP 的全部 CONFIG | 用 `c_s_axis_s2mm_tdata_width` |
| `Cannot change read-only property 'offset'` | 想手工固定 DMA 地址 | 报错原文 | 交给 `assign_bd_address`，PYNQ 从 `.hwh` 读真实地址 |
| `The following clock pins are not connected to a valid clock source: /ps7/M_AXI_GP0_ACLK` | 只给从设备接了时钟 | 报错列出引脚 | PS 的 AXI 端口也要显式接 FCLK |
| `No interface pins matched 'get_bd_intf_pins hdmi_in/out_stream'` | 端口在层次里，实际路径是 `/video/hdmi_in/out_stream` | `get_bd_intf_pins -hier -filter {NAME =~ "*stream*"}` | 用实际层次路径，或用 `get_bd_intf_nets -of_objects <pin>` 按端口删网络 |

## 5. PYNQ 上板

| 现象 | 触发条件 | 定位方法 | 修复 |
| --- | --- | --- | --- |
| `Overlay` 报找不到 `.hwh` | `.bit` 与 `.hwh` 基名不同 | 看目录 | 两者必须同名（`sobel_dma.bit` + `sobel_dma.hwh`） |
| `no AXI DMA in overlay` | 位流没加载成功，或 DMA 未例化 | 打印 `ol.ip_dict` | 先跑 `skill/overlay_check` 离线校验 `.hwh` |
| `ol.axi_dma_0` 没有 `sendchannel` | 某些 PYNQ 版本只绑 `DefaultIP` | `hasattr(dev,'sendchannel')` | 用 `pynq.lib.dma.DMA(ol.ip_dict[name])` 包一层 |
| DMA `wait()` 永不返回 | 内核按 `TLAST` 断行但整帧一次传输；或流没接上 | 先跑单行传输 | 按行传输（本项目 DMA 版）或加 TLAST 生成器 |
| 自定义 overlay 载入后 `.video` 不存在 | `pynq.lib.video` 要求层次名为 `video` 且含 `axi_vdma` | `ol.ip_dict` | 保留 VDMA 实例即可，即使不接数据 |

## 6. Git / 环境（最容易造成"文件消失"的一类）

| 现象 | 触发条件 | 定位方法 | 修复 |
| --- | --- | --- | --- |
| 一堆目录从工作区消失、但 `git status` 说"干净" | 在仓库**子目录**里执行 `git sparse-checkout set ...`（git 会向上找到仓库根） | `git ls-files -v` 出现 `S` 标记；`git config core.sparseCheckout` 为 true | `git sparse-checkout disable`，文件原样回来 |
| `git clone` 报 `schannel: AcquireCredentialsHandle failed` | 受限 shell 下 Git 的 schannel 后端拿不到凭据 | 报错原文 | `git -c http.sslBackend=openssl clone ...` |
| PowerShell 重定向的日志打开是乱码/有 NUL | `python ... > file` 时重定向编码不一致 | 十六进制看有 `00` | 由 Python 自己写文件，或统一 UTF-8 |

## 使用建议

- **遇到报错先在本表里按现象搜一遍**，多数坑的修复只有一行；
- 新坑请连同"触发条件"一起补进来——只写"某某命令失败"对别人没有价值；
- 这份清单与 `report/ai_collaboration_log.md` 互补：那里记"什么时候踩的、怎么发现的"，
  这里记"怎么快速定位和修"。
