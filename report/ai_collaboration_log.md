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
