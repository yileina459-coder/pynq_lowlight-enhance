# 大模型协作记录

赛规要求提交"体现大模型协作过程的交互记录，含提示词、模型回答与自我纠错轨迹"（占 15 分中的一部分）。
本文件按时间顺序记录**真实发生**的协作过程：我问了什么、模型做了什么、哪里错了、怎么纠正的、依据是什么。
不美化、不删错误——纠错轨迹本身是评分点。

格式约定：

- **日期 / 阶段**：对应 `docs/roadmap.md` 的阶段编号
- **我的提示词**：尽量还原原话
- **模型产出**：做了什么，落到哪个文件
- **错误与纠正**：模型错了什么，我（或验证）怎么发现的
- **人工判断**：哪些决定是队员拍的，不是模型拍的

---

## 2026-10-18 / P0 环境基线

### 交互 1：让模型通读全部资料

**提示词**
> 我参加这一届FPGA的AMD赛道的自选赛题，一些相关内容全在这个文件夹中。你先全部浏览一遍

**模型产出**
- 遍历仓库（14 个文件 + 2 份 PDF），指出 `src/sim/build/board/data/skill/report` 全为空壳
- 发现两份 PDF 无法直接读（目录里没有 PDF 解析库、没有 pdftotext），自行写了一个
  PDF 文本提取脚本（`.tmp/pdftext.py`），提取出选题指南 25 页与选题笔记 2 页全文
- 归纳出赛道规则要点：初级组资格、器件范围、工具版本、5 项评分权重、目录英文命名要求、决赛英文海报
- 指出仓库里 `xlicdiag.rpt` 显示许可异常（`No SERVER lines in license file`），列为风险

**错误与纠正（第一次）**
第一版提取器把中文输出成一堆乱码。原因是：只支持了 `bfrange` 的 `<lo> <hi> <dst>` 形式，
而这两份 PDF 用了 `[<d1> <d2>]` 数组形式；另外把 `(en-US)` 这类 `/Lang` 属性当成正文抽了出来。
修正后仍有一处乱码：PowerShell 的重定向把 Python 的 UTF-8 输出写成了 UTF-16，
读回时被当成单字节文本，还产生 18995 个 NUL 字符。改为**由 Python 自己写文件**（`open(..., encoding='utf-8')`）后正常。

**人工判断**
- 确认了"初级组"报名身份与 PYNQ-Z2 的合规性
- 确认了分辨率先做 720p（PYNQ-Z2  HDMI 端口的官方上限）

### 交互 2：开始实际开发

**提示词**
> 我需要你逐步辅助我完成这个项目。

**模型产出**
- 自动侦察环境：找到 Vivado/Vitis 装在 `D:\AMD_vivado_vitis\2026.1`
- 发现 `vitis_hls` 命令不存在，写包装脚本 `tools/env/vitis_hls.bat`
- 跑通两个冒烟工程并入库：`build/smoke/vivado`（综合）、`build/smoke/hls`（C 仿真 + 综合 + 导出 IP）
- 落文档 `docs/env.md`、`docs/roadmap.md`

**错误与纠正（第二次）**
1. 包装脚本第一版只调了 Vitis 的 `setupEnv.bat`，`export_design` 报
   `Cannot find Vivado, please check XILINX_VIVADO`。原因是 HLS 的 `export_design`
   依赖 `XILINX_VIVADO`，而 Vitis 自己的 settings 不含它。修正：先 call Vivado 的
   `.settings64-Vivado.bat`，再进 loader。
2. 在这个终端里跑 EDA 直接被环境挡住：Vivado 写 `%APPDATA%\Xilinx` 失败，Vitis 的
   C 仿真报 `cat.exe: couldn't create signal pipe`。这不是工程问题，记录进 `docs/env.md`，
   后续 EDA 命令改为放宽权限执行。

---

## 2026-10-18 / P2 第一个 HLS 算子（Sobel）

**提示词**
> 我就只有一个笔记本电脑 / 我是零基础，你看着来，可以上github或者其他网站搜索类似开源项目作为参考

**模型产出**
- 写流式 Sobel 核：`src/hls/sobel/{sobel.hpp,sobel.cpp}`
- 写独立的 C++ 黄金模型测试台：`src/hls/sobel/tb_sobel.cpp`（推 3 帧，检查帧边界上的行缓冲轮转）
- 写 Python 黄金参考与 bit-exact 比对：`sim/sobel/golden_sobel.py`
- 生成 720p 测试图与参考输出：`data/images/test_720p.png`、`data/reference/sobel_720p.png`
- 结果：C 仿真 9216 拍 0 误差；II=1；Fmax 141.9 MHz；BRAM 3 / DSP 2 / FF 583 / LUT 809
- 检索并读了三份同类开源项目，写进 `docs/references.md`

**错误与纠正（第三次）**
1. `ap_int` 的三元表达式 `gx < 0 ? -gx : gx` 编译报
   `conditional expression is ambiguous; ap_int<17> can be converted to ap_int<16> and vice versa`
   ——取负会让位宽加 1。修正：先算 `neg_gx`/`neg_gy` 两个同宽临时量再选择。
2. 第一版像素接口写死 24 bit，而 AXI DMA 只能搬 32 bit 字，会导致中间要塞一个
   4:3 的位宽转换器（不可实现）。修正：把 `SOBEL_PIX_W` 做成可配置宏，
   DMA 路线用 32、HDMI 路线用 24，核只取低 24 位、其余位透传。

**人工判断**
- 边界策略（水平复制、垂直用上一帧行）由模型提出、队员确认：它直接决定"能否和软件参考逐位对上"
- 比对标准定为 **bit-exact（0 个通道不一致）**，不接受 PSNR 阈值

---

## 2026-10-18 / P3a DMA 版 overlay（不需要显示器的验证路线）

### 交互：继续自主推进

**提示词**
> （目标轮次自动继续）继续完成项目

**模型产出**
- `build/overlay_dma/`：一条 `build.bat` 走完 解包 HLS IP → 建块设计（PS + AXI DMA + sobel_stream）→
  实现 → 出位流 → 从 XSA 拆出 `sobel_dma.bit` / `sobel_dma.hwh`
- `board/dma_sobel/`：上板脚本 `sobel_dma.py`（逐行 DMA）、`demo.ipynb`、README
- `sim/sobel/test_sobel_dma_offline.py`：用 numpy 假 DMA 复现核行为，**在主机侧先验证上板脚本**
- `skill/overlay_check/`：上板前离线校验 `.hwh`

**实测结果**（`build/overlay_dma/out/`）：WNS **+3.086 ns**（100 MHz 下满足时序）、
LUT 4027（7.57%）、FF 5645（5.31%）、BRAM 3.5（2.5%）、DSP 3（1.36%）。

**错误与纠正（第四次～第八次，全部是工具链细节，但每一条都能卡住一天）**

1. `CONFIG.c_m_axis_s2mm_tdata_width` 不存在（CRITICAL WARNING: Parameter does not exist）。
   AXI DMA 的 S2MM 流位宽参数叫 `c_s_axis_s2mm_tdata_width`（slave 侧）。
   修正方式：先用一个 60 行的探测脚本把 IP 的合法参数全打印出来，再改，而不是靠猜。

2. `set_property offset ... [get_bd_addr_segs ...]` 报 `Cannot change read-only property 'offset'`。
   修正：删掉手工地址，交给 `assign_bd_address` 自动分配——PYNQ 是从 `.hwh` 读真实地址的，
   手工指定只会增加冲突风险。

3. `validate_bd_design` 失败：`/ps7/M_AXI_GP0_ACLK` 与 `/ps7/S_AXI_HP0_ACLK` 没有时钟。
   PS 的 AXI 端口也要显式接 `FCLK_CLK0`，不只是从设备要接。

4. `Expand-Archive` 拒绝解压 `.xsa`（只认 `.zip`）。XSA 本质是 zip，改用
   `System.IO.Compression.ZipFile::ExtractToDirectory`。

5. `.hwh` 解析失败：2026.1 的属性是大写 `INSTANCE`/`MODTYPE`，时钟频率放在
   `<PORT CLKFREQUENCY="...">` 而不是 `<CLOCK>` 元素。第一版解析器按旧格式写，输出全空。
   修正后兼容两种写法——这也是 `skill/overlay_check` 要打印原始清单的原因。

6. PYNQ 版本差异：`ol.axi_dma_0` 在某些版本是 `DefaultIP`（没有 `sendchannel`）。
   `find_dma()` 改成"拿不到 DMA 驱动就用 `pynq.lib.dma.DMA` 包一层"，避免版本差异直接崩。

**人工判断**
- 主路线仍是 HDMI 流式；DMA 版是"没有显示器也能证明硬件正确"的过渡验证
- DMA 按行传输的帧率**不代表**最终性能，只用于功能验证；真实性能在 P3b 测

---

## 2026-10-18 / P3a 收尾与 P3b 预研

**模型产出**
- DMA overlay 位流构建完成并入库（`board/dma_sobel/sobel_dma.bit`）：WNS **+3.086 ns**、
  LUT 4027（7.6%）、FF 5645（5.3%）、BRAM 3.5（2.5%）、DSP 3（1.4%）
- `board/ps_baseline/ps_sobel.py`：PS 侧 numpy 基线（与 PL 同算法同边界），
  主机实测 1280x720 约 **40 ms/帧**（24.6 fps），板上 ARM 会慢数倍
- `docs/p3b_plan.md`：查证 PYNQ v3.1.2 的 base overlay 源码（`boards/Pynq-Z2/base`，
  4448 行、Vivado 2024.1 生成、带版本门禁），给出两条移植路线与风险

**错误与纠正（第九次，这次是操作事故，不是代码 bug）**

在 `.tmp/PYNQ` 里做稀疏检出时，有一条 `cd PYNQ` 因为上一步 clone 失败而没有生效，
命令继续在 `.tmp` 下执行 `git sparse-checkout set boards/Pynq-Z2`。由于 `.tmp` 在仓库内部，
git 向上找到了本仓库的 `.git`，于是**把比赛仓库本身设成了稀疏检出**，
`src/ sim/ build/ skill/ report/ data/` 从工作区消失，并且因为 skip-worktree 位，
`git status` 还显示"干净"——这是最危险的地方：不看文件系统就会误以为没事。

恢复：`git sparse-checkout disable`，所有已提交文件原样回来（因为都已在 0b68874 里）。
复核：`src/hls/sobel/*`、4 MB 位流、测试图都在。

教训（值得写进踩坑清单）：
1. 任何 `git` 子命令在仓库子目录里都可能作用于**整个仓库**，稀疏检出尤其危险；
2. `git status` 显示干净 ≠ 文件都在，稀疏检出会用 skip-worktree 把缺失隐藏掉；
   判断依据应该是 `git ls-files -v`（有 `S` 标记）与文件系统的交叉验证。

---

## 2026-10-18 / P3b：base overlay 移植到 2026.1（本轮主线）

**提示词**
> （目标轮次自动继续）继续完成项目

**模型产出**
- `build/overlay_hdmi/`：`fetch_pynq.ps1`（按 v3.1.2 稀疏克隆 PYNQ）、
  `patch_base_tcl.py`（3 个补丁）、`insert_sobel.tcl`（切断 VDMA 环回并插入内核）、
  `build.bat`（7 步流水线）
- 关键结论：**PYNQ 官方 base overlay 可以在 Vivado 2026.1 里原样重建**，
  不需要 `upgrade_ip`，也不需要退回 2025.2
- 内核在 7 ns 目标下收敛：估计 Fmax **194.59 MHz**、II=1（视频时钟 142.86 MHz）
- `board/hdmi_stream/`：上板脚本（加载 overlay、配置 HDMI、启动管线）

**错误与纠正（第十次～第十五次）**

1. **版本门禁**：`base.tcl` 头部的 `scripts_vivado_version 2024.1` 会让脚本在 2026.1 里
   直接 `return 1`。改成 2026.1。
2. **PFM_NAME**：脚本末尾 `PFM_NAME {xilinx.com:xd:${overlay_name}:1.0}` 在花括号里，
   Tcl 从不替换变量，2024.1 不校验所以没人发现，2026.1 校验并报
   `PFM_NAME name '${overlay_name}' is not valid`。改成字面量 `base`。
3. **HLS IP 缺失**：base.tcl 列出的 5 个 `xilinx.com:hls:*` IP 在 IP 目录里根本没有
   （仓库只给源码，不给打包好的 zip）。必须先跑 `build_ip.tcl`，而它 `exec vitis_hls`，
   本机 vitis_hls 不在 PATH → 把 `tools/env` 加进 PATH。
4. **PATH 被自己覆盖**：在 `cmd /c "call settings64.bat && set PATH=...;%PATH%"` 里，
   `%PATH%` 在整行解析时就展开了（此时还没 call settings64），结果 Vivado 反而找不到。
   教训：PowerShell 里先设 `$env:PATH`，cmd 里不要再动 PATH。
5. **BOM 让 Tcl 崩溃**：用 PowerShell `Set-Content -Encoding UTF8` 生成的 .tcl 带 BOM，
   Vivado 报 `invalid command name "﻿open_project"`。所有 .tcl 一律用不带 BOM 的方式写。
6. **端口路径猜错**：`get_bd_intf_pins hdmi_in/out_stream` 找不到——实际路径是
   `/video/hdmi_in/out_stream`（`video` 是顶层层次）。用
   `get_bd_intf_pins -hier -filter {NAME =~ "*stream*"}` 一次列全，比猜快。
7. **顺序问题**：`get_property ip_repo_paths [current_project]` 在 `open_project` 之前调用，
   报 `No projects are currently open`。必须先开工程、再设 IP 仓库、然后打开块设计。
8. **两处小坑**：`vitis_hls -f script.tcl` 的 `$argv` 里含有 `-f` 和脚本名，
   解析自定义参数时不能按下标取；`create_bd_cell` 前必须 `update_ip_catalog`，
   否则报 `IP definition not found for VLNV`。

**人工判断**
- 视频通路选择"绕过 VDMA 直通"，换来约一行延迟；代价是 PS 侧不能再 `readframe()`，
  这条取舍写进了 `board/hdmi_stream/README.md`

---

## 2026-10-18 / P3b 收尾：HDMI overlay 位流建成

**提示词**
> 运行失败的再尝试一次

**结果**
- `board/hdmi_stream/sobel_hdmi.bit`（3.9 MB）+ `sobel_hdmi.hwh`（4.3 MB）构建成功；
- 实现结果：**WNS +0.207 ns**（142.857 MHz，0 个失败端点）；LUT 62.2%、FF 43.8%、
  BRAM 57.5%、DSP 9.6%（框架占大头，Sobel 核约 1%）；
- `.hwh` 通过 `skill/overlay_check`：188 个模块、`sobel_0` 在位、`ap_clk` = 142.857 MHz。

**错误与纠正（第十六次～第十八次）**

1. **OOC 综合的两种失败模式**。base overlay 有近 200 个 IP，默认每个 IP 一个
   out-of-context 综合 run。
   - `-jobs 4` 并发时，多个子进程同时加载 Vivado 的 Tcl app store，报
     `Could not open 'C' for writing` / `tclapp::load_apps failed`；
   - `-jobs 1` 不会撞，但在 32 核机器上串行跑 200 个 run 要几个小时（实测 95 分钟只完成 ~112 个）。
   最终有效做法是**低并发重跑**：已完成的 run 走 IP 缓存，只剩上次失败的 4 个 run，
   `-jobs 2` 大约 15 分钟就收敛到出位流。
2. **"整体综合"这条路没走通**。原本想让所有 IP 走 `synth_checkpoint_mode None`，
   避免逐 IP 的 OOC run；但 `get_ips` 对**块设计内部**的 IP 返回空列表，
   脚本里那句计数打印出来是 `IPs switched to global synthesis: 0`，等于没生效。
   这一点已写进 `build_bitstream.tcl` 的注释，避免下一个人以为它有用。
3. **`axi_vdma` 不是 `axi_dma`**。`skill/overlay_check` 原来只认 AXI DMA，
   对 HDMI overlay（用的是 VDMA）误报 FAIL。修正为两者都算 DMA 通道。

**人工判断**
- 接受 WNS 只有 +0.207 ns 的现实：视频时钟固定 142.857 MHz，base overlay 本身就吃掉大部分时序余量；
  自研核在 7 ns 下估计 194.59 MHz，说明瓶颈在框架不在核。若要更大余量，得裁掉框架里用不到的
  MicroBlaze/音频/IO 子系统（会破坏 PYNQ `BaseOverlay` 的 API，暂不做）。

---

## 2026-10-18 / P3a 完成：板上逐位一致，PS/PL 对比 4.7×

**结果**
- 板上 `python3 sobel_dma.py` → **`COMPARE PASS (bit-exact)`**，0/2764800 个通道不一致；
- PL：659.1 ms/帧（1.516 fps、1.397 Mpixel/s）；
- PS（同板 ARM Cortex-A9 + numpy）：3108.4 ms/帧（0.320 fps、0.30 Mpixel/s）；
- **加速比 4.72×**，且两边输出逐像素完全一致（`golden_compare` 比对 0 不一致）。

**错误与纠正（第十九次～第二十一次）**

1. **有界核的 AXI-Lite 控制没接**。把 DMA 路线换成 `sobel_bounded`（ap_ctrl_hs）后重建，
   板上 `ol.ip_dict` 里只有 `axi_dma_0` 和 `ps7`——`sobel_0` 根本不在地址映射里。
   原因：`sc_ctrl` 只连了 DMA 的 `S_AXI_LITE`，核的 `s_axi_control` 悬空，
   `ap_start` 无处可写。修法：`sc_ctrl` 改成 `NUM_MI=2`，补一条 `M01_AXI → sobel_0/s_axi_control`。
   教训：**加带寄存器的 IP 时，"接上流"和"接上控制"是两件独立的事，漏掉后者不会报错，
   只会表现成"设备不存在"。**

2. **自由运行核在流结束时不排空流水线**。这是这次最花时间的根因：给 1280 拍输入，
   出来的不足 1280 拍，DMA 于是永远等不到 TLAST。判定方法是"传输结束差多少"——
   每次正好差 16 个字（一个 AXI burst），再配合"2560 拍传输在第 1280 拍被提前关闭"
   证明了 TLAST 生成器本身没问题，问题在核的输出拍数。

3. **板上跑任何脚本都要 sudo + venv 解释器**。PYNQ 3.1.1 的 Jupyter 以 root 运行，
   XRT 设备只有 root 能开；直接 `python3` 用的是 `/usr/bin/python3`（没有 pynq）。
   正确写法：`sudo env XILINX_XRT=/usr PATH=/usr/local/share/pynq-venv/bin:... /usr/local/share/pynq-venv/bin/python3 xxx.py`。

**人工判断**
- 接受"逐行 DMA"的 659 ms 作为**功能验证**数据，并在报告里明确标注它的开销主要来自
  720 次核启动 + 1440 次传输的软件开销，而不是算子；整帧传输列为下一步优化。
- 主机 numpy（40.7 ms/帧）比板上 PL 还快这件事，如实写进报告，避免"加速比"被误解。

---

## 2026-10-18 / 整帧 DMA：15.8 ms/帧，196.7×

**结果**
- 整帧一次传输：**15.8 ms/帧（63.45 fps、58.47 Mpixel/s）**，比逐行快 41 倍；
- 相对 PS numpy（3108.4 ms/帧）**196.7×**；
- 仍然 **bit-exact**（0/2764800 通道不一致）。

**错误与纠正（第二十二次～第二十三次）**

1. **DMA 长度寄存器只有 14 位**。整帧 3.6 MB 一传，运行时报
   `ValueError: Transfer size is 3686400 bytes, which exceeds the maximum DMA buffer size 16383`。
   `c_sg_length_width` 这个参数名听起来是 Scatter-Gather 专用，实际也决定简单模式的
   缓冲区长度寄存器宽度。改成 23 位（8 MB）后整帧传输才成立。
2. **TLAST 生成器在整帧模式下反而有害**。它按拍计数，在整帧传输里会在第 1280 拍
   提前"关闭"传输。既然有界核已经会把自己接收到的 TLAST 原样送出去，索性把它从块设计里去掉
   （RTL 保留在仓库里作为记录），并让核用 `line_width` 自己数行边界——
   这样无论软件怎么切分传输，核的行结构都不受影响。

**人工判断**
- 对比表同时保留"逐行 4.7×"和"整帧 196.7×"两档，并说明前者是软件开销、后者才是
  "算子 + DDR 带宽"的真实水平；只报最好看的数字会掩盖工程过程。
- 把 15.8 ms 与理论计算量（1280×720 在 100 MHz、II=1 下约 9.2 ms）对照写进报告，
  读者能看出还剩下多少优化空间（DDR 往返与启动开销约占 6.6 ms）。

---

## 2026-10-19 / 采集卡到货前，把增强核先证明掉

**结果**
- 板上 AXI-DMA 整帧回环，7 个预设（pass / clarity / reading / night / invert / binarize / split）
  **各 0/2764800 通道不一致**，15.6 ms/帧；
- 新增 `board/enhance_dma/`（位流 + 测试脚本 + 证据图 + metrics），WNS **+2.182 ns**；
- 结论：增强核的算术与 59 位配置寄存器都已在硅片上验证，剩下只差"接上 HDMI 看画面"。

**错误与纠正（第二十四次～第二十六次）**

1. **寄存器偏移不能硬编码**。我按"每 4 字节一个标量"写了 `n_pixels=0x10, knee=0x24, ...`，
   板上脚本的映射自检直接报错：HLS 2026.1 实际按 **8 字节**间隔排（0x10/0x18/0x20/…/0x60）。
   修法：偏移从 overlay 的 `ip_dict` 寄存器表读取，脚本只保留寄存器"名字列表"。
   教训：**自检要在写第一个寄存器之前做**，否则这类错会表现成"硬件算错了"。
2. **边界语义要用约定，不要靠猜**。首轮 `pass` 和 `binarize` 逐位一致，其余预设差 1~15 个灰度级，
   且第一处不一致总在左边界。原因不是算术：硬件的行缓冲在新帧开头装的是**上一帧的行**，
   即 wrap 语义，而黄金模型默认 replicate。改成 `--border wrap`（与 Sobel 参考图同一约定）后全 0。
3. **AXI-Lite 接口名由 bundle 决定**。`#pragma HLS INTERFACE s_axilite ... bundle = ctrl`
   生成的接口是 `s_axi_ctrl` 而不是 `s_axi_control`，第一次块设计连接因此失败。

**人工判断**
- 把"增强核算得对"和"接上 HDMI 看得到"拆成两件事分别取证：前者现在就能做，后者必须等采集卡。
  这样 10/22 到货后只剩集成与观察，不再有"算法到底对不对"的不确定性。
- 没有为有界版本单独写 C 仿真：流式版本已覆盖同一套算术，而板上零容差比对是更强的证据；
  这一点在 `src/hls/enhance/enhance_bounded.cpp` 与 README 里都写明了，不含糊过去。

---

## 2026-10-19（续） / 发现预设会把暗页黑白翻转，补了一个 `document` 预设

**结果**
- 板上 8 个预设全部逐位一致（新增 `document`），15.6 ms/帧；
- 量化了 `reading` 在暗页上的问题：字迹 62.7→62.8、纸面 21.4→114.1，对比度 **+41 → −51（极性翻转）**；
- 新增 `document`（clarity=20, knee=192, lo=64, hi=12）：对比度 **+158**，黑像素 0.2%，
  过曝 3.7%，板上同样逐位一致。

**错误与纠正（第二十七次）**

`reading` 预设的 knee=48 低于纸面亮度，导致"纸面走低段被 ×5.5 提亮、字迹走高段被压向拐点"，
于是字比纸暗。这不是硬件错，是**参数与场景不匹配**。修法不是改硬件，而是加一个
knee 高于纸面的预设，并把搜索过程写成可复现脚本（`sim/enhance/tune_document_preset.py`，
评分函数：正对比度、少黑像素、少过曝）。

**人工判断**
- 没有直接改 `reading` 的参数：它来自另一轮标定，且已被引用；改动会让已有材料与截图对不上。
  新增预设是增量、可复核的做法，并在文档里同时列出两组的实测数字。
- 明确写了"这是合成暗页上的结果，真实画面到货后需重新标定"——避免把一次离线搜索吹成结论。

---

## 2026-10-19（续二） / 延迟从"约一行"变成"16 个像素时钟"

**结果**
- 板上实测：**16 个像素时钟 = 160 ns @100 MHz**（720p60 的一行是 17.2 µs，即 <1% 行）；
- 实现方式：`axis_cycle_stamp` 在内核**前后各一个**，同一时钟同一复位，两个时间戳相减；
- 同轮还把输出与黄金模型的零容差比对保持住了（`reading` 15.6 ms/帧，0/2764800）。

**错误与纠正（第二十八次～第三十次）**

1. **戳内核的 AXI-Stream 引脚会让 TVALID/TREADY 脱离接口网**。第一版监视器用
   `connect_bd_net` 直接连 `enhance_0/s_in_TVALID` 等，Vivado 报
   `BD 41-759 ... tied-off to all 0's`，而且 impl 直接失败。改成"串在通路里的直通单元"才对
   （和自己写的 `axis_tlast_gen` 一个套路）。
2. **直通单元上"在飞像素数"恒为 0**。因为 `m_tvalid = s_tvalid`、`s_tready = m_tready`，
   进出同拍触发 —— 计数器的定义本身在这个位置不可观测。板上读到的 0 是"正确地测了一个无用的量"。
3. **单个直通单元的"首拍时间戳"也恒相等**。同一原因。必须在内核前后各放一个，才能得到内核延迟。

**人工判断**
- 三次返工都发生在"观测点位置"上，而不是算术上。教训记进坑表：
  **测延迟要在被测模块的两侧取样，不能在它旁边取样**。
- 16 这个数字与综合报告里的流水线深度（`depth = 17`）一致，所以它是可信的，不是凑出来的。
- 报告里同时保留了"约一行"的原始表述并说明它是**上界**，避免前后数字看起来矛盾。

---

## 2026-10-19（续三） / 增强核进了 HDMI 位流，时序从 −1.333 ns 救回 +0.242 ns

**结果**
- `board/hdmi_stream_enhance/enhance_hdmi.bit`：WNS **+0.242 ns**、0 失败端点、hold +0.014 ns；
  LUT 63.1%、BRAM 57.5%、DSP 10.9%；
- 板上加载成功（23 个 IP、`video` 绑定、HDMI IN/OUT 层次都在），配置 GPIO 写 `document` 与
  `binarize` 两个预设都能原值回读，延迟 GPIO 两通道都是输入；
- 没有 HDMI 源，两个时间戳停在 0 —— 脚本把它写成"预期"，不当成测量结果。

**错误与纠正（第三十一次～第三十三次）**

1. **首轮 impl 时序失败：WNS −1.333 ns，59 个失败端点。** 看报告发现根本不是我担心的内核算术，
   而是**配置 GPIO（100 MHz）→ 内核配置寄存器（142.86 MHz）的 CDC 路径**，要求 1 ns。
   这本质是静态配置信号，不该按同步路径约束。
2. **XDC 不是脚本文件。** 第一版约束里写了 `set`/`puts`/`if`，Vivado 报
   `Designutils 20-1307 ... not supported`，然后**静默地什么都没约束**，所以重跑一轮时序一点没变。
   改成纯 `set_false_path` 语句后一次通过。
3. **`git add -A` 把 `.work/` 扫进了提交**（PYNQ 源码树 + 嵌套仓库，277 个文件）。推送前用
   `reset --soft` 重写提交修掉，并把 `build/**/.work/` 加进 `.gitignore`。

**人工判断**
- 没有为了过时序去改内核算法（那会动到已经逐位验证过的算术）。这 1.3 ns 的代价来自两个不同
  时钟域之间的静态配置总线——按 CDC 处理才是正确的工程做法，而且我在 XDC 里写清了"什么时候
  会看到什么"（换预设时最多一帧参数混用）。
- 也没有把"加载成功"说成"画面验证"。截图与端到端延迟仍然只能等采集卡。
