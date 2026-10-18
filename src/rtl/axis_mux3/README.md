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

- 已写自检 testbench：`tb_axis_mux3.v`，检查三件事——选中通路数据/TLAST 不被篡改、
  三路都被持续排空（计数 ≥150）、切换中途不丢拍；
- **本机尚未跑通仿真**：`xsim` 在批处理模式下一启动就崩溃
  （`Could not open file mapping object (2)` 后 `EXCEPTION_ACCESS_VIOLATION`，两次复现）。
  这是 xsim 在本机环境的运行问题，不是设计问题，但也意味着**这份 RTL 目前是"未验证"状态**。

在交互式终端里重跑（很可能就正常了，xsim 对会话环境敏感）：

```powershell
cd build\rtl\axis_mux3
..\..\..\tools\env\vivado.bat -mode batch -source run_sim.tcl
```

期望最后一行 `AXIS_MUX3 TB PASS`。

## 现状

该模块**尚未**被插入任何 overlay。当前 `board/hdmi_stream/sobel_hdmi.bit` 里只有 Sobel 一路。
等 HDMI 版上板验证通过、再决定是否把三路并行 + 本选择器加进去（会增加约 2% 的资源，
但当前实现的 WNS 只有 +0.207 ns，需要先评估时序）。
