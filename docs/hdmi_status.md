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
4. 排查工具已就位：`board/hdmi_stream_enhance/hdmi_hpd_retry.ipynb`（拉低再拉高 HPD，监视 60 秒）、`hdmi_stock_check.ipynb`（原厂对照）。

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

`board/hdmi_stream_enhance/hdmi_loopback_ours.ipynb`：用**我们的位流**做
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
