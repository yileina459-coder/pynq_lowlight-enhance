# HDMI 源码研究：为什么输入锁不上（2026-10-20 夜）

> 这份文件是逐行读 `dvi2rgb` IP 源码、PYNQ `base.tcl` 和 PYNQ 驱动源码之后的结论，
> 目的是把"HDMI IN 不锁"从猜测变成可验证的推理链。

## 一、`dvi2rgb` 的时钟要求（源码依据）

`dvi2rgb.vhd` 的 generic：

```vhdl
kEmulateDDC  : boolean := true;   -- 用 FPGA 模拟 DDC EEPROM（提供 EDID）
kRstActiveHigh : boolean := true;
kAddBUFG     : boolean := true;
kClkRange    : natural := 2;      -- MULT_F = kClkRange*5 (>=120MHz=1, >=60MHz=2, >=40MHz=3)
kEdidFileName: string  := "900p_edid.data";
```

`TMDS_Clocking.vhd` 里 MMCM 的实际配置：

```vhdl
CLKFBOUT_MULT_F  = kClkRange * 5.0
CLKOUT0_DIVIDE_F = kClkRange * 1.0     → 输出 = 5 × 输入（5 倍串行时钟）
CLKIN1_PERIOD    = kClkRange * 6.0 ns  → PLL 内部假定的输入周期
```

关键约束写在源码注释里：

```
FVCO = FIN × MULT_F，Artix-7 -1 速度等级要求 600 MHz ≤ FVCO ≤ 1200 MHz
720p 的 TMDS 时钟是 74.25 MHz
  → MULT_F = 10（kClkRange=2）时 FVCO = 742.5 MHz ✓
  → MULT_F = 5 （kClkRange=1）时 FVCO = 371.0 MHz ✗ 低于下限
1080p 的 TMDS 时钟是 148.5 MHz
  → MULT_F = 5 （kClkRange=1）时 FVCO = 742.5 MHz ✓
  → MULT_F = 10（kClkRange=2）时 FVCO = 1485 MHz ✗ 高于上限
```

**结论 1**：`kClkRange` 必须与输入分辨率匹配，选错就永远锁不上，且没有任何软件层能补救。

## 二、PYNQ 原厂配置的矛盾

`base.tcl`（Pynq-Z2）：

```tcl
set_property -dict [list \
  CONFIG.kAddBUFG {false} \
  CONFIG.kClkRange {1} \
  CONFIG.kEdidFileName {720p_edid.data} \
  CONFIG.kRstActiveHigh {false} \
] $dvi2rgb_0
```

- EDID 只报 **720p**（74.25 MHz）；
- 却把 PLL 配成 **kClkRange=1**（≥120 MHz 档）。

两者矛盾：源端按 EDID 送 720p，板子的 PLL 期望 ≥120 MHz，FVCO 只有 371 MHz，**不可能锁定**。
这解释了为什么**原厂 `base.bit` 也锁不上笔记本的 720p**。

我们构建的位流已把 `kClkRange` 改为 **2**，并在综合后网表里确认：

```
CLKFBOUT_MULT_F  = 10.0
CLKIN1_PERIOD    = 12.0 ns
CLKOUT0_DIVIDE_F = 2.0
```

## 三、EDID 本身是合法的

`720p_edid.data` 不是二进制文件，而是 **128 行、每行 8 位二进制**的文本（VHDL 初值格式）。
按正确格式解析：

```
header      : OK (00 FF FF FF FF FF FF 00)
checksum    : 0xee，sum mod 256 = 0  OK
manufacturer: 4GL   product 0x0002
EDID version: 1.3
preferred   : 1280x720 @ 60.0 Hz, 74.25 MHz, total 1650x750
name        : "DigilentDVI-2"
```

**结论 2**：EDID 合法、时序正确，不是"EDID 坏了导致源端不送信号"。

## 四、复位与时钟的连锁关系

`base.tcl`：

```tcl
connect_bd_net -net dvi2rgb_0_aPixelClkLckd \
    [get_bd_pins dvi2rgb_0/aPixelClkLckd] [get_bd_pins aPixelClkLckd]
...
connect_bd_net -net hdmi_in_aPixelClkLckd \
    [get_bd_pins hdmi_in/aPixelClkLckd] [get_bd_pins proc_sys_reset/aux_reset_in]
```

即：**输入像素时钟 PLL 未锁 → `aPixelClkLckd=0` → 前端复位保持 → 整条输入通路停摆**。
而它"锁没锁"没有接到任何可读寄存器，PS 侧只能通过 `video.hdmi_in.mode` 间接判断。

**结论 3**：这是一个闭环依赖——没有 TMDS 就没有时钟，没有时钟就没有 lock，没有 lock 就复位前端。
所以"mode=None"只能说明"没收到可锁的信号"，无法区分"源端没送"和"板子收不到"。

## 五、To-Be-Verified：我们自己的输出端

原厂 overlay 能让采集卡**从兜底彩条变成全黑**（=锁上了、但没画面内容）；
我们的 overlay 插入内核后，采集卡始终显示兜底彩条（=没有 TMDS）。

已知与输出相关的配置：

| 项目 | 值 | 来源 |
| --- | --- | --- |
| `rgb2dvi` 的 kClkRange | 2（60–120 MHz） | base.tcl |
| 输出时序 | `vtc_out`，由 `video.hdmi_out.configure(mode)` 设置 | PYNQ 驱动 |
| 输出启动 | `video.hdmi_out.start()`（必须单独调用） | `dvi.py` 源注释 |
| 像素时钟 | `axi_dynclk`，寄存器读回与时钟锁定位正常 | `hdmi_out_state.py` |

**待验证的假设**：`v_axi4s_vid_out` 是否在等一个 SOF（TUSER）才开始出帧。
我们的内核把上游 TUSER 原样透传；如果输入永不上锁，就没有 TUSER，OUT 可能一帧都不发。
这也解释了"原厂黑屏（VDMA 一直在喂数据）vs 我们全无信号（没有数据进来）"。

## 六、明天的判定路径（按成本排序）

1. **自环**（一根线 OUT→IN）+ 我们的位流（输入 range 2、输出 range 2，两者都适合 720p）：
   若锁上 → 板子收发都好，问题在笔记本；若锁不上 → 板子侧硬件/前端问题。
2. **自环 + 原厂位流**只能证明一半：原厂输入 range 1（1080p）、输出 range 2（720p），
   两者无交集，**不能**用来判断对错，这一点之前没意识到，记下来避免再浪费时间。
3. 若自环失败：在 `v_axi4s_vid_out` 的 `tvalid/tready/tuser/tlast` 上插 ILA，直接看它为什么不发帧。

## 七、这次研究纠正的两个错误判断

- 之前以为"改 kClkRange 就能解决笔记本 720p"，但当时没有验证 **IP 是否重新综合**；
  现在已从综合后网表确认 MULT_F=10 真的进了位流。
- 之前打算用"原厂 overlay 自环"做对照，读了源码才发现原厂输入/输出档位无交集，那个实验设计是错的。
