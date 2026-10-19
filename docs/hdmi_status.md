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
