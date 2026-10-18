# axis_mux3 — 三选一 AXI4-Stream 选择器

## 用途

把三个并行运行的算子（Sobel / Gaussian / Sharpen）的输出接到同一路显示通路上，
由 PS 写一个 2 位选择信号决定**显示哪一个**。这是 P4"算子切换 + UI"的硬件基础。

```text
                  ┌─ sobel_0   ─┐
 pixel_pack ──┬───┼─ gaussian_0─┼─── axis_mux3 ── pixel_unpack
              │   └─ sharpen_0 ─┘        ▲
              │                          │
              └──── axis_broadcast       sel[1:0] ← PS（AXI-Lite 寄存器）
```

## 关键设计：未选中的两路要"排空"，不能"暂停"

三个算子对同一输入流是一拍进一拍出的（II=1），如果对未选中的算子拉低 `TREADY`，
背压会通过 `axis_broadcast` 传回上游，把被选中的那一路也一起卡住——画面就停了。

所以这里的策略是：

| 端口 | TREADY |
| --- | --- |
| 被选中的输入 | 跟随下游 `m_tready`（真正反压） |
| 未选中的输入 | 恒为 1（收下并丢弃） |

这样三个算子始终保持同步，切换时不会出现"某一台落后几十行"的错位。

## 接口

只带 `TDATA / TVALID / TREADY / TLAST`。像素流在 `pixel_pack` 与 `pixel_unpack` 之间
就是这四根线；不引入 `TUSER/TKEEP` 可以少动 base overlay 的时序。

- 组合逻辑选择，**零附加延迟**，一拍进一拍出；
- `sel == 3` 视为非法，回落到输入 0，不产生 X 态。

## 验证状态（如实记录）

**已做的**：

- 自检 testbench `tb_axis_mux3.v`：检查选中通路数据/TLAST 不被篡改、三路都被持续排空
  （每路计数 ≥150）、切换中途不丢拍、`sel==3` 回落到输入 0；
- `xvlog` 编译 + `xelab` 展开**均通过**（说明 RTL 本身语法与层次没问题）；
- **Vivado 综合通过**（7 ns 约束、`xc7z020clg400-1`）：`0 errors, 0 critical warnings`，
  资源 **36 LUT、0 FF**，纯组合逻辑因此没有内部时序路径（WNS 显示 NA 是预期的）。
  报告在 `build/rtl/axis_mux3/mux3_util.rpt`、`mux3_timing.rpt`。

**未做的**：功能仿真（跑 testbench 本身）。

`xsim` 在本机一启动就崩：

```text
Could not open file mapping object (2).
Time resolution is 1 ps
Abnormal program termination (EXCEPTION_ACCESS_VIOLATION)
```

三次复现（含用户放行安全提示后重试、以及绕过 Vivado 直接用 `xvlog/xelab/xsim`），
都是**同一个位置**：快照建好了、仿真内核初始化时打不开共享内存映射。
这是运行环境（安全软件/进程限制）问题，不是设计问题，但也意味着**功能正确性目前只有
静态检查 + 综合背书，没有仿真背书**。

在你这台机器的交互式终端里重跑（很可能就正常）：

```powershell
cd C:\Users\79171\Desktop\FPGA\build\rtl\axis_mux3
..\..\..\tools\env\vivado.bat -mode batch -source run_sim.tcl
```

期望最后一行 `AXIS_MUX3 TB PASS`。

## 现状

该模块**尚未**被插入任何 overlay。当前 `board/hdmi_stream/sobel_hdmi.bit` 里只有 Sobel 一路。
等 HDMI 版上板验证通过、再决定是否把三路并行 + 本选择器加进去（会增加约 2% 的资源，
但当前实现的 WNS 只有 +0.207 ns，需要先评估时序）。
