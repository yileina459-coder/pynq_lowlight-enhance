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
