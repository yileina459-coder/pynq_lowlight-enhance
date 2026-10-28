# 环境基线（已验证）

本文件记录"这台机器上的工具链到底能不能出结果"，以及复现所需的入口脚本。
所有结论都有一次实际运行的输出为证，不是照着教程抄的。

## 1. 已验证的事实

| 项目 | 结论 | 证据 |
| --- | --- | --- |
| Vivado | v2026.1（64-bit），SW Build 6511674 | `vivado -version` |
| Vitis / Vitis HLS | v2026.1，C 仿真 / C 综合 / 导出 IP 全部通过 | `build/smoke/hls/` |
| 许可 | Vivado Design Suite **BASIC**，有效期至 **2027-09-16** | 综合日志 `A valid Vivado Design Suite BASIC license has been detected` |
| 目标器件 | `xc7z020clg400-1`（PYNQ-Z2）综合成功 | `build/smoke/vivado/` |
| HLS 结果 | `II=1`，估计 Fmax ≈ 203 MHz（10 ns 约束） | `build/smoke/hls/` 综合日志 |
| PYNQ-Z2 板卡文件 | **未安装**（Vivado `data/boards/board_files` 中无 Pynq-Z2） | 目录检查 |
| 网络 | github.com / pypi.org / fpgachina.cn 均可访问 | `Test-NetConnection` |

## 2. 两个必须记住的坑

### 2.1 2026.1 的 Windows 安装缺 `vitis_hls.bat` 启动器

安装目录里有 `Vitis\bin\unwrapped\win64.o\vitis_hls.exe`，但没有随附的
`vitis_hls.bat`，所以命令行里直接敲 `vitis_hls` 会报"不是内部或外部命令"；
而直接运行那个 `.exe` 又会报 `RDI_DATADIR is not set`。

解决办法：用本仓库的包装脚本，它照抄了官方启动器的做法并补上 `XILINX_VIVADO`：

```bat
tools\env\vitis_hls.bat -version
tools\env\vitis_hls.bat -f build\smoke\hls\run_hls.tcl
```

`XILINX_VIVADO` 是必须补的，否则 `export_design -format ip_catalog` 会报
`Cannot find Vivado, please check XILINX_VIVADO environment variable`。

### 2.2 在这个终端里跑 EDA 需要放宽沙箱

Vivado 要写 `%APPDATA%\Xilinx\Vivado\2026.1\`（Tcl 目录、IP 缓存），
Vitis HLS 的 C 仿真要由 msys2 的 `cat.exe` 创建信号管道。在默认的
工作区写沙箱下，前者报

```
Failed to write app catalog file 'C:/Users/<user>/AppData/Roaming/Xilinx/Vivado/2026.1/...'
```

后者报

```
cat.exe: *** fatal error - couldn't create signal pipe, Win32 error 5
```

两者都不是工程问题。用自己的终端（或普通 PowerShell）直接跑这些命令没有此问题。

## 3. 复现步骤

```powershell
# 1) 综合冒烟（约 1 分钟）
cd build\smoke\vivado
..\..\..\tools\env\vivado.bat -mode batch -nojournal -nolog -source synth_smoke.tcl
#    期望最后一行：RESULT: OK

# 2) HLS 冒烟（约 1 分钟）
cd build\smoke\hls
..\..\..\tools\env\vitis_hls.bat -f run_hls.tcl
#    期望：CSIM 打印 SMOKE PASS，最后一行 RESULT: OK，
#    并在 export\stream_smoke.zip 生成可导入 Vivado 的 IP
```

## 4. 许可的边界

BASIC 许可覆盖 7 系列器件与常用的 AXI/VDMA 等 IP，够本项目用。但要注意：

- 若后续用到需要更高许可等级的 IP，综合/实现会直接报 license 错误，需要提前确认；
- 报告里必须写明工具版本与许可类型：读者拿到的是别家的许可，脚本要能独立复现。

## 5. 板卡文件

- PYNQ-Z2 板卡文件不是必须装的：`board/` 上板工程会用到 `xc7z020clg400-1`，
  用器件直连可以绕开，但 board flow 更规范。
