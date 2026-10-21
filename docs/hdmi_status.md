# HDMI 排查交接（2026-10-19 晚）

> 这份文件是给"明天继续"用的：现状、已排除的假设、下一步该怎么查。
> 一句话结论：**增强核本身已完全验证（DMA 通路逐位一致 + 面板演示），
> HDMI 的两个方向都卡在集成/硬件层，且都不影响交付。**

## 一、已验证好的（可以写进报告，不用再动）

| 证据 | 数字 | 位置 |
| --- | --- | --- |
| DMA 通路 8 预设逐位一致 | 各 0/2764800 通道 | `board/enhance_dma/` |
| 整帧吞吐 | 15.6 ms/帧、63 fps、58 Mpixel/s | `board/enhance_dma/metrics_enhance.csv` |
| 流水线延迟（DMA） | 16 像素时钟 = 160 ns @100 MHz | `axis_cycle_stamp` ×2 |
| PS vs PL（Sobel） | 3108.4 ms → 15.8 ms，**196.7×** | `report/comparison.md` |
| 交互面板 | 8 预设可切换、实时显示三项指标 | `board/enhance_dma/panel.ipynb` |

## 二、HDMI IN：EDID/HPD 正常，TMDS 锁不上

**已确认的事实**

- 把 HPD 拉高后，Windows 设备管理器会多出 `Generic Monitor`，**拔掉采集卡 USB 也不消失** → 这个显示器是板子提供的，EDID 通了；
- 但 `video.hdmi_in.mode` 始终是 `None`；
- **原厂 `base.bit` 也一样锁不上** → 与我们的设计无关；
- 设计侧已排除：`dvi2rgb` 的 EDID 文件是 `720p_edid.data`、`RefClk` 接 `clk_200M`、`aRst_n` 接 `periph_resetn_clk100M` 且已释放。

**下次的排查顺序**

1. **换 HDMI 线**（最高优先）——用"笔记本直连采集卡能出图"的那根线接笔记本→板子 IN；
2. 换信号源（手机 USB-C→HDMI、另一台电脑）；
3. 若仍不行，怀疑板子 HDMI IN 的 DDC/TMDS 引脚（拍接头针脚照片）；
4. 排查工具已就位：`board/hdmi_stream_enhance/notebooks/hdmi_hpd_retry.ipynb`（拉低再拉高 HPD，监视 60 秒）、`hdmi_stock_check.ipynb`（原厂对照）。

## 三、HDMI OUT：板子能出信号，我们插入内核后不产生 TMDS

**已确认的事实**

- 原厂 overlay + `writeframe()` 时，采集卡**从"兜底彩条"变成"全黑"** → 说明锁到了有效信号（画面黑是内容问题）；
- 我们的 overlay（`enhance_hdmi.bit` 与 `enhance_pattern.bit`）→ 采集卡始终显示**兜底彩条** = 没有 TMDS；
- 两边寄存器读数**完全一致**：`dynclk STATUS=0x1`(PLL 锁定)、`vtc control=0x03f7ef06`、`vtc status=0x00013000`；`_display.state()=1`、`mode()` 正确返回 1280x720；
- 一个尚未证实的疑点：像素是否**连续**流动。`axis_cycle_stamp` 只锁存"第一个拍"，所以即使后续被反压卡住，延迟读数仍然是 21，看不出停流。

**下次的下一步（按顺序）**

1. **确认数据是否连续流动**：给 `axis_cycle_stamp` 加 `beats_in/beats_out` 计数输出（或另写一个计数器单元），接到 `gpio_enh_lat` 的两个通道，间隔 1 秒读两次——数字在涨说明流没停；
2. **若流停了**：查 `v_axi4s_vid_out` 的 `tready`，以及 `pixel_unpack` 是否需要额外配置（PYNQ 的 `VideoOut.configure()` 只设了 bpp，帧尺寸由 VDMA 提供）；
3. **若流没停但无 TMDS**：在 `v_axi4s_vid_out` 的 `tvalid/tready/tuser/tlast` 上插 ILA（`overlay_hdmi_enhance` 工程可直接加）；
4. 对照实验：原厂 overlay 里用 `writeframe()` 写**纯色帧**，确认采集卡能显示彩色而不是黑屏——这一步能区分"VDMA 没喂数据"还是"vid_out 不输出"。

## 四、明天的建议顺序（时间有限）

1. **先录面板演示视频**（`panel.ipynb`，点 3 个预设各停 2 秒）——这是交付底线，30 分钟能拿到；
2. 用 OBS 录；截图 3 张（pass/document/binarize，含右侧数字）；
3. 把截图和视频发我 → 我把证据补进报告与海报；
4. 有余力再回 HDMI（先换线试 HDMI IN，成本最低）。

## 五、板子上的文件位置（关机不丢）

```
/home/xilinx/jupyter_notebooks/enhance_dma/    panel.ipynb、enhance_dma.py、bit/hwh
/home/xilinx/jupyter_notebooks/hdmi_enh/       hdmi_check / hdmi_demo / hdmi_stock_check / hdmi_hpd_retry
/home/xilinx/jupyter_notebooks/hdmi_pattern/   pattern_demo.ipynb、enhance_pattern.bit
```

板子重启后**只需重新加载 overlay**（notebook 第一格会自动加载）。

---

## 2026-10-20 夜：源码研究的结论

完整推导见 `docs/hdmi_source_study.md`，这里只记结论和明天的动作。

**新的确定性结论**

1. `kClkRange` 决定 MMCM 的 `MULT_F = kClkRange*5`，Artix-7 -1 要求
   `600 <= FVCO <= 1200 MHz`。720p 的 TMDS 时钟 74.25 MHz **必须用 range 2**；
   原厂用 range 1 → FVCO=371 MHz，**物理上不可能锁定**。这解释了原厂 base.bit 也失败。
2. 我们重建的位流已确认把 `kClkRange` 改成 2，并在**综合后网表**里核实
   `CLKFBOUT_MULT_F=10.0 / CLKIN1_PERIOD=12.0`——修复真的进了位流。
3. `720p_edid.data` 是 128 行二进制文本，解析后**完全合法**
   （头部 OK、校验和 OK、首选时序 1280x720@60 / 74.25 MHz、名称 DigilentDVI-2）。
   所以不是 EDID 坏了导致源端不送信号。
4. `aPixelClkLckd` 接到 `proc_sys_reset` 的 `aux_reset_in`：
   **没有 TMDS → 没有像素时钟 → PLL 不锁 → 前端一直复位**。
   因此 `mode=None` 无法区分"源端没送"还是"板子收不到"。

**因此明天只剩一个实验需要做**

`board/hdmi_stream_enhance/notebooks/hdmi_loopback_ours.ipynb`：用**我们的位流**做
OUT→IN 自环，720p。选我们的位流而不是原厂，是因为原厂输入 range 1、输出 range 2，
两端没有交集，那个实验设计本身就是错的（今晚读源码才发现）。

| 结果 | 结论 | 下一步 |
| --- | --- | --- |
| 锁上（黑屏也算） | 板子收发都正常 | 问题在笔记本侧：接 IN、设 720p，必要时用"列出所有模式"强制 |
| 仍不锁 | 输出端不发 TMDS（与采集卡现象一致） | 在 `v_axi4s_vid_out` 的 `tvalid/tready/tuser/tlast` 上插 ILA |

**顺带准备**：`src/rtl/axis_cycle_stamp` 已加 `beats` 输出（拍数计数），
用来区分"流水线在跑"和"跑了 21 拍就停了"。BD 里那两个 cell 是模块引用，
加端口后需要**重建 cell**（`update_module_reference` 不刷新端口表）——
`build/overlay_hdmi_enhance/rebuild_stamps.tcl` 就是干这个的，但今晚没跑通
（新 cell 仍缺 `beats` 端口），明天先解决这个再插 ILA。

## 备忘：这轮踩过的两个坑

- **改 IP 参数后要回读验证**：`get_bd_cells` 默认只看顶层，`dvi2rgb` 在 `video` 层级里，
  不加 `-hierarchical` 就一个都匹配不到，属性没写进去却毫无报错。
- **删工程会丢 Vivado 的 IP 缓存**：为改一个参数重跑 `base.tcl`，导致 ~200 个 OOC 综合
  重来一遍（约一小时）。正确做法是在现有工程上改属性再 `impl`。

---

## 2026-10-22 凌晨：HDMI 输出打通（640x480），以及为什么只能 640x480

### 结论一：这块板子的 HDMI 输出只能稳定驱动 640x480

用**原厂 overlay**（不含我们任何改动）逐模式测"VDMA 能否消费一帧"——`writeframe()`
只有在 VDMA 完成一次帧传输后才返回，所以它是与采集卡无关的客观判据：

| 模式 | 像素时钟 | `writeframe` | 采集卡 |
| --- | --- | --- | --- |
| 640x480 | 25.175 MHz | 立即返回 | **出现画面** |
| 800x600 | 40 MHz | 阻塞 | 无信号 |
| 1280x720 | 74.25 MHz | 阻塞 | 无信号 |
| 1920x1080 | 148.5 MHz | 阻塞 | 无信号 |

PYNQ-Z2 的两个 HDMI 口是**无缓冲直连 PL** 的（手册 3.1.13），所以输出能力受限于
管脚驱动与信号完整性。这不是我们的设计问题——原厂位流同样如此。

### 结论二：HDMI 输入无法工作在 640x480

`dvi2rgb` 的 `kClkRange` 只有 **1/2/3** 三档（设 5 会被 IP 拒绝：

```
ERROR: [IP_Flow 19-3461] Value '5' is out of the range for parameter
       'TMDS clock range(kClkRange)'
```

25.175 MHz 需要 5 档（VCO = 25.175 × 25 = 629 MHz 才在 600–1200 内）；最高档 3
只能给 377 MHz，低于下限，输入端锁不上。

**因此 640x480 的 HDMI 直通在这块板子上不可实现**，除非更换输入 IP。

### 结论三：交付的演示改由 VDMA 供帧

`build/overlay_hdmi_enhance/source_from_vdma.tcl` 把内核输入从
`video/hdmi_in/out_stream` 改为 `video/axi_vdma/M_AXIS_MM2S`：

```
PS 写帧到 DDR  ->  VDMA MM2S  ->  stamp_in -> enhance -> stamp_out
               ->  pixel_unpack -> v_axi4s_vid_out -> rgb2dvi  ->  HDMI OUT (640x480)
```

内核仍在像素通路上、仍是硬件实时处理、预设与延迟测量都保留，只是帧来源变成 PS。
板端实测（`board/hdmi_stream_enhance/hdmi_vdma_demo.py`）：

```
hdmi_out running at 640x480
test image (480, 640, 3), mean 124.0
[01:56:06] preset clarity   writeframe 6.5 ms  latency 21 pixel clocks
[01:56:14] preset document  writeframe 6.4 ms  latency 21 pixel clocks
[01:56:31] preset invert    writeframe 6.5 ms  latency 21 pixel clocks
[01:57:36] preset binarize  writeframe 6.5 ms  latency 21 pixel clocks
```

`writeframe` 6.4 ms 表示 VDMA 持续消费（输出端真的在跑），21 拍是两道时间戳
夹出来的流水线延迟。演示循环的 7 档预设（8 个里的 reading 未纳入循环）跑满 3 轮无异常。

### 结论四：三个把排查带偏的坑（都已修正）

1. **`video.hdmi_in.mode` 读的不是输入检测值**，而是 VDMA 的配置值，只在
   `VideoIn.configure()` 里被赋值。没调 `configure()` 就永远是 `None`，
   于是"没锁上"其实是"没配置过"。真正的检测只能用
   `video.hdmi_in._hdmi.start(init_timeout=...)`，它报的错误是
   `No incoming video signal detected`。
2. **`rgb2dvi` 的 `kClkRange` 在这套设计里无效**：`kGenerateSerialClk=false`，
   串行时钟由 `axi_dynclk` 的 `PXL_CLK_5X_O` 提供，ClockGen 根本没实例化。
   之前反复改这个参数毫无效果，原因在此。
3. **多个 PYNQ 进程同时存在会互相抢 VDMA 与显示**，表现为"明明跑通了又变彩条"。
   每次测试前必须确认只有一个进程（`ps aux | grep hdmi_`），否则结论不可信。

### 现在的位置

| 项目 | 状态 |
| --- | --- |
| 内核在 HDMI 输出链路上实时工作 | ✅ 已上板（640x480，21 拍延迟） |
| 演示循环的 7 档预设实时切换 | ✅ 已上板 |
| HDMI 输入（720p/1080p） | ✅ 能锁 1080p，但输出端无法同分辨率工作 |
| HDMI 直通 640x480 | ❌ 输入 IP 的 kClkRange 不支持 |
| 端到端低延迟演示 | ⚠️ 受硬件限制，改由 VDMA 供帧 |

---

## 2026-10-22 凌晨（二）：预设为什么只有一半生效——HLS 把配置锁存了

### 现象

画面实时可见（内容变化能立刻看到），但切换预设时画面不动。排查后画面其实
**变了一次**：`pass` → `night` 时明显变亮，说明配置链路是通的，只是**部分参数**无效。

### 根因（生成 RTL 里的铁证）

`build/overlay_hdmi_enhance/.work/enhance_ip/hdl/verilog/enhance_stream.v`：

```verilog
reg [0:0] binarize_read_reg_1446;      // 配置被存进寄存器
reg [0:0] mono_read_reg_1437;
1872: binarize_read_reg_1446 <= binarize;   // 只在流水线 prologue 采一次
2312: y3 = (binarize_read_reg_1446 == 1'b1) ? ... // 之后永远用旧值
```

而 `clarity` 是组合直连的：

```verilog
2340: assign zext_ln129_1_fu_387_p1 = clarity;
```

逐项核对结果：

| 配置项 | 生成 RTL 里的状态 | 结论 |
| --- | --- | --- |
| `clarity` | 组合直连 | **实时生效** |
| `gain_lo` | 组合直连 | **实时生效** |
| `gain_hi` | 组合直连 | **实时生效** |
| `knee` | `knee_read_reg_*` | 启动时锁存 |
| `thresh` | `thresh_read_reg_*` | 启动时锁存 |
| `binarize` | `binarize_read_reg_*` | 启动时锁存 |
| `invert` | `invert_read_reg_*` | 启动时锁存 |
| `mono` | `mono_read_reg_*` | 启动时锁存 |
| `split_x` | `split_x_read_reg_*` | 启动时锁存 |

### 为什么会这样

内核是**自由运行**的（`ap_ctrl_none` + `while (1)` + `#pragma HLS PIPELINE II=1`）。
对流水线里的**循环不变量输入**，HLS 会把读取提到循环的 prologue 并用寄存器锁存一次
（节省寄存器、缩短关键路径）。普通 `ap_ctrl_hs` 内核每帧重新 start，prologue 会重跑，
所以看不出问题；而 `ap_ctrl_none` 内核的 prologue **只跑一次**，于是这 6 个参数
永远停在第一个值上。

### 修法（三选一，按改动量排序）

1. **复位内核**：把 `enhance_0/ap_rst_n` 与一个 GPIO 位相与，PS 改完配置后拉低几拍。
   改动最小（一个 `util_vector_logic` + 一个 GPIO 位 + 一次重建），代价是复位瞬间
   有 1 帧花屏。
2. **配置走 BRAM**：把这 6 个参数改成从一块小 BRAM 读取（`volatile` 指针 +
   `#pragma HLS INTERFACE bram`），AXI BRAM Controller 由 PS 写入。存储器读取
   HLS 无法提到循环外，语义最干净，但要改 HLS + 重建 IP + 重建 overlay。
3. **配置走 AXI-Lite 寄存器**：把这 6 个参数改成 `s_axilite`。仍可能被 HLS 视为
   循环不变量，需实测确认，不如方案 2 可靠。

### 对交付的影响

- HDMI 通路上**已经能演示实时参数调节**（`clarity`/`gain_lo`/`gain_hi`），
  例如 `pass` ↔ `night` 的亮度变化在采集卡上清晰可见；
- **8 个预设的完整切换**目前只在 AXI-DMA 通路上被逐位验证过（`board/enhance_dma/`，
  8 预设 × 0/2764800 通道不一致），HDMI 通路需要按上面方案 1 或 2 重建后才能全量演示。

---

## 2026-10-22 晚：修复完成，运行期预设切换在 HDMI 上生效

### 修法（方案 1：改配置后复位内核）

新增 `src/rtl/enh_rst_gate/enh_rst_gate.v`：

```verilog
assign ap_rst_n = aresetn & ~cfg_hi[31];
```

`cfg_hi[31]` 是第二配置字里的空闲位（`enh_cfg_split` 只用 26:0），PS 用它请求复位。
`build/overlay_hdmi_enhance/add_kernel_reset.tcl` 把这个门控插在
`rst_ps7_0_fclk1_peripheral_aresetn` 与 `enhance_0/ap_rst_n` 之间，
其余 4 个同域外设仍接原来的复位网络。

PS 侧时序（`board/hdmi_stream_enhance/hdmi_live.py` 的 `write_preset`）：

```python
write(GPIO_DATA,  lo)                 # 先放好只在 prologue 采样的参数
write(GPIO2_DATA, hi | RST_BIT)       # 断言内核复位
sleep(0.002)
write(GPIO2_DATA, hi)                 # 释放 → prologue 重新采样
```

顺序很关键：**参数先就位，再释放复位**，prologue 采到的就是新值。

### 板端验证

`hdmi_preset_stream.py --a pass --b binarize --preset-hold 12`，3 分钟 14 次切换，
每次切换后延迟仍稳定为 **21 个像素时钟**（内核复位后能正常重启）。

采集卡截图（`board/hdmi_stream_enhance/evidence/`）：

| 文件 | 画面特征 |
| --- | --- |
| `hdmi_preset_02_pass.png` | 平滑渐变 + 灰色带 + 黑色文字条 + 三色块，即原始测试图 |
| `hdmi_preset_03_binarize.png` | 大面积黑 + 底部一条白带（阈值切分生效） |
| `hdmi_preset_01_document.png` | 暗部抬起、中段变亮，文字条更清楚 |
| `hdmi_preset_04_high_gain.png` | 过曝、高对比，色块饱和 |

四张图互不相同，与四个预设的数学效果一致 —— **配置在运行期真的生效了**。

### 现在的完整状态

| 能力 | 状态 |
| --- | --- |
| HDMI 输出（640×480，板子上限） | ✅ 已上板 |
| 内核在像素通路上实时处理 | ✅ 已上板，延迟 21 拍 |
| 演示循环的 7 档预设运行期切换 | ✅ 已上板，截图证据 4 张 |
| 8 个预设逐位一致性 | ✅ DMA 通路 0/2764800（`board/enhance_dma/`） |
| 每次换预设的当帧花屏 | ⚠️ 已知代价（复位清空 line buffer）；方案 2（配置走 BRAM）可消除 |
| HDMI 直通（笔记本→板子→显示） | ❌ 受限于输出只能 640×480 而输入 IP 不支持该模式 |

### 采集序列（2026-10-21 20:29–20:35，连续运行中截图）

用户在同一次连续运行里截了 17 张画面，逐张判读后归档在
`board/hdmi_stream_enhance/evidence/`：

| 文件 | 画面 |
| --- | --- |
| `hdmi_capture_plain.png` | 原始状态：平滑渐变、灰带、黑色文字条、色块 |
| `hdmi_capture_split.png` | **垂直分屏**：左 1/3 保持原样，右侧被处理 |
| `hdmi_capture_binarize.png` | **硬阈值**：大面积黑 + 一条白带 |
| `hdmi_capture_sharpened.png` | 高对比/过锐状态 |
| `hdmi_capture_glitch.png` | 换预设当帧的花屏（复位清空 line buffer） |
| `hdmi_presets_2x2.png` | 上面四张的 2×2 拼图，用作海报配图 |

**关于闪烁**：用户在第 7、11、15 张附近观察到画面不稳定。这正是文档里记录的
"换预设当帧花屏"——`enh_rst_gate` 复位内核时 line buffer 被清空，下一帧才恢复。
属于设计取舍，不是随机故障。

**判读依据**：截图按"画面里能看到什么"命名（垂直分界、硬阈值、过锐、原始），
而不是按 PC 时间戳去猜当时是哪个预设——板子的时钟和 PC 不同步，硬对时间会引入
错误结论。要严格对上档名，需要跑一次由日志实时报档名的采集。

### 2026-10-22 21:30：复位门控改为异步断言 / 同步释放

**现象（用户观察）**：换预设时不是"当帧花屏一下"，而是**某些预设下画面持续闪烁**，
其他预设稳定。这个区别很关键——瞬态花屏和状态异常是两种失效。

**根因**：第一版门控是纯组合的

```verilog
assign ap_rst_n = aresetn & ~cfg_hi[31];
```

`cfg_hi` 来自 100 MHz 的 PS 域，内核跑在 142.857 MHz。复位**释放**落在内核时钟的
任意相位上，内核可能带着错乱的 line-buffer 指针退出复位 → 该预设下持续闪烁，
直到下一次复位碰巧落在好的相位。

**修法**：`src/rtl/enh_rst_bridge/enh_rst_bridge.v`，标准的异步断言 / 同步释放：

```verilog
wire rst_n_async = aresetn & ~cfg_hi[31];
always @(posedge aclk or negedge rst_n_async)
    if (!rst_n_async) sync <= 2'b00;
    else              sync <= {sync[0], 1'b1};
assign ap_rst_n = sync[1];
```

约束侧：这条跨时钟路径按设计就是**异步断言**，不做时序检查，因此在 `cdc.xdc` 里加了

```tcl
set_false_path -from [get_cells -hier -filter {NAME =~ "*gpio_enh_cfg*"}] \
               -to   [get_cells -hier -filter {NAME =~ "*enh_rst_bridge*"}]
set_false_path -to [get_pins -hier -filter {NAME =~ "*enh_rst_bridge*/sync_reg*/CLR"}]
```

补约束前实现报 `WNS −1.377 ns / 2 个失败端点`（`gpio2_Data_Out_reg[0]` →
`sync_reg[0]/CLR` 的 recovery 检查）；补后 **WNS +0.171 ns，0 失败端点**。

**另一个坑**：给 `enh_rst_gate` 加时钟端口后，BD 里的 cell 仍报
`the gate has no aclk pin`——Vivado **按模块名缓存 module reference**，同名重建也没用。
换成新模块名 `enh_rst_bridge` 才拿到新端口表。之前 `axis_cycle_stamp` 加 `beats`
端口失败也是同一原因（当时没识别出来）。

**板上验证**：`hdmi_vdma_demo.py --cycle 12` 跑 2.5 轮、18 次切换，延迟全程 21 个
像素时钟、`writeframe` 稳定 6.5 ms，无异常。

### 2026-10-22 22:00：闪烁的真正原因——复位截断流后输出核欠载

**现象**：预设切换有画面，但部分档位持续在"图像 ↔ 几乎全黑"之间交替。

**排除过程（每一步都有客观判据，不靠肉眼）**

| 假设 | 判据 | 结果 |
| --- | --- | --- |
| 帧缓冲里有未写入的黑帧，VDMA 轮转到它 | `hdmi_probe_buffers.py` 读回 4 块缓冲：`mean=131.5, max=235` | ❌ 排除 |
| 输出链路本身不稳 | 静态灰面保持 85 秒，延迟恒定 21 拍 | ❌ 排除 |
| OBS 缩放高频内容产生锯齿 | 采集源改 640×480（1:1）后仍闪 | ❌ 排除 |
| 反复写 DDR 造成撕裂 | 只写一帧仍闪 | ❌ 排除 |
| 复位释放相位错乱 | 已改异步断言/同步释放，时序 +0.171 ns | ✅ 已修，但闪烁仍在 |
| **复位截断像素流 → `v_axi4s_vid_out` 欠载 → 采集卡自行重锁** | 主动重启输出链路后消失 | ✅ **根因** |

**修法**：每次切预设（内核复位）之后，**确定性地重启输出链路**，而不是让采集卡
自己挣扎着恢复：

```python
write_preset(cfg, name)                 # 复位内核，prologue 重新采样配置
out.stop()
out.configure(VideoMode(640, 480, 24, 60))
out.start()
for _ in range(4):                      # 填满 4 块帧缓冲
    f = out.newframe(); f[:] = image; out.writeframe(f)
```

**板上验证**：`hdmi_preset_only.py --cycle 15 --total 220`，15 次切换、每次都重启输出链路，
延迟全程 21 个像素时钟。用户确认："稳了，只在切换瞬间闪一下。"

**现在的演示主脚本**：`board/hdmi_stream_enhance/hdmi_preset_only.py`。
其余带"循环写帧"或"只复位不重启输出"的脚本只保留作排查记录，不再作为演示路径。

### 最终采集序列（2026-10-22 22:15，稳定版演示）

`hdmi_preset_only.py --cycle 15`（每次切预设后重建输出链路）连跑 5 分钟，用户按档位截图，
归档在 `board/hdmi_stream_enhance/evidence/`：

| 文件 | 画面 |
| --- | --- |
| `hdmi_final_a_plain.png` | 干净原图：平滑渐变、灰带、黑色文字条、三色块 |
| `hdmi_final_b_brighter.png` | 明显提亮，渐变上出现细密竖纹（增益效果） |
| `hdmi_final_c_dark.png` | 暗场，文字条被拎出、色块发闷 |
| `hdmi_final_d_desaturated.png` | 强烈去色/反相倾向 |
| `hdmi_final_e_inverted.png` | 暗场竖纹 + 亮文字条 |
| `hdmi_final_f_split.png` | **约 2/3 处出现垂直分界：左侧原样、右侧被处理** |

`hdmi_final_f_split.png` 是最有说服力的一张：**同一帧里同时存在"原样"和"处理后"两块区域**，
直接证明内核在实时处理这条像素流，而不是 PS 事后合成的图。

文件按"画面里能看到什么"命名，不按 PC 时间戳硬对档名——板子时钟与 PC 不同步。

### 2026-10-22 深夜：自选图片输入

新增三个文件：

| 文件 | 作用 |
| --- | --- |
| `tools/make_frame.py` | 电脑侧：任意图片 → 640×480×3 裸 RGB（letterbox 或 crop） |
| `tools/check_frame.py` | 校验 PC 与板侧测试图**逐字节一致**、通道顺序、尺寸 |
| `board/.../hdmi_show_image.py` | 板侧：显示裸 RGB 或图片文件，可轮播预设 |
| `board/.../notebooks/hdmi_panel.ipynb` | 新增"选择图片"上传单元格 |

**遇到的两个问题**

1. 首次 `writeframe` 偶发无限阻塞（VDMA 一直等不到整帧完成），原因是采集卡还没锁定
   时序就没人消费。修法是加**看门狗 + 重试**：4 秒不返回就重启输出链路重试，
   三次都失败才报错并提示"检查采集卡/OBS"。
2. 内核换成 BRAM 版之后画面全黑且 `writeframe` 永久阻塞——接线脚本按**小写**后缀查
   引脚（`s_out_tdata`），而 HLS 生成的是 `s_out_TDATA`，`get_bd_pins -quiet` 把失败
   咽了下去，于是内核输出侧全部**悬空**。判据很明确：网络名等于引脚名
   （`/enhance_cfg_0_s_out_TDATA`）就说明它没连上别的东西。修正后加了自动检查，
   悬空会直接报错。

### 2026-10-22 凌晨：配置改走 BRAM，切换闪烁彻底消失

**问题**：换预设时画面会黑一下。原因是配置必须在端口上，HLS 把循环不变量的 9 个参数
锁在流水线 prologue 里，而自由运行内核只跑一次 prologue——所以改参数必须复位内核，
复位又打断像素流、让 `v_axi4s_vid_out` 欠载，只能事后重建输出链路。

**做法**：新增 `enhance_stream_cfg`，配置从一块 64 位存储器读，**每像素重读一次**。
内存读无法被提到循环外，参数因此变成实时的。切预设只剩一次寄存器写。

**关键细节：地址必须是运行期值**

第一版写 `ap_uint<64> cfg[1]` 并读 `cfg[0]`。HLS 证明下标是常量，把数组折成一个普通
64 位输入端口，于是标志位又被锁存：

```verilog
binarize_reg_1458 <= cfg[32'd40];     // 还是一次性采样
```

改成让下标依赖运行时数据（`cfg_index` 由 `col` 决定，实践中恒为 0）之后，HLS 只能生成
真正的存储器端口，生成 RTL 变成：

```verilog
binarize_reg_1575 <= cfg_Dout_A[32'd40];   // 每周期无条件重采样
```

综合结果：**II = 1，估计 Fmax 194.59 MHz**，与端口版本一致。

**存储器**：`src/rtl/cfg_bram/cfg_bram.v`，两个 64 位字、真双口、写侧 100 MHz（PS 域）、
读侧 142.857 MHz（像素域）。小块存储器必须用 `xpm_memory_tdpram` 显式例化：起初写成
`(* ram_style = "block" *) reg [63:0] mem [0:1]`，Vivado 因为只有两项而推断成触发器，
跨时钟就成了受时序检查的同步路径——**WNS −1.393 ns、59 个失败端点**。换成 XPM 后
跨时钟发生在原语内部（按字原子），**WNS +0.289 ns、0 失败端点**。

**上板实测（2026-10-22 09:09，新位流）**

```
frames written : 741
write time     : min 2.1 ms, median 2.2 ms, max 17.1 ms
stalls > 60 ms: 0
latency values : [21]
RESULT: LIVE SWITCH STABLE
```

判据是客观的：切预设期间**持续写帧 741 次、25 次切换**，`writeframe()` 只在 VDMA 完成
一帧后才返回，因此任何一次流中断都会表现为一次长写。最长 17.1 ms（远低于一帧 16.7 ms
量级），延迟全程 21 拍——**没有任何一次复位、没有中断、画面不黑**。

