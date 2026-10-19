# hdmi_pattern — 板内图案源，不依赖任何外部 HDMI 输入

```
video_pattern_gen ─► stamp_in ─► enhance ─► stamp_out ─► HDMI OUT ─► 采集卡
```

## 为什么有这个目录

HDMI IN 这条路上，板子能完成 EDID 握手和 HPD（Windows 设备管理器里会出现
`Generic Monitor`），但一直锁不上笔记本送来的 TMDS。为了不让演示和录视频卡在这一点上，
这个 overlay 把输入换成了**FPGA 内部生成的图案**：

- 采集卡上能直接看到图案被实时增强，换预设画面立刻变；
- 它同时**验证 HDMI OUT 与采集卡这一段**：这里出画面就说明输出链路是好的，
  唯一还有疑问的就是输入；
- 报告里必须如实写成「内部图案源 / 合成信号」，不能冒充真实摄像头输入。

## 运行

```bash
cd /home/xilinx/jupyter_notebooks/hdmi_pattern
# 固定一个预设
sudo env XILINX_XRT=/usr PATH=/usr/local/share/pynq-venv/bin:/usr/bin:/bin HOME=/root \
  /usr/local/share/pynq-venv/bin/python3 pattern_demo.py --preset document

# 每 4 秒换一个预设（录视频用）
sudo env XILINX_XRT=/usr PATH=/usr/local/share/pynq-venv/bin:/usr/bin:/bin HOME=/root \
  /usr/local/share/pynq-venv/bin/python3 pattern_demo.py --cycle 4
```

板上实测输出：

```text
hdmi_out configured: 1280x720 @60
the capture card should now show colour bars with a white block
[03:56:19] preset document  latency 21 pixel clocks (~0.147 us at 142.857 MHz)
```

**21 个像素时钟 = 147 ns** 是 HDMI 通路上第一次量到的真实流水线延迟（DMA 通路是 16 拍 @100 MHz
= 160 ns；两条通路时钟不同，像素数也不同，差异来自 `v_axi4s_vid_out` 前后的额外级）。

## 图案内容

- 8 条彩条（白/黄/青/绿/品红/红/蓝/黑）—— 色调曲线、反色、单色会立刻改变它；
- 底部 80 行**灰阶阶梯** —— 观察对比度与二值化阈值；
- 中部一个**移动白块** —— 静态截图看不出动，采集卡上能看出它在跑。

## 文件

| 文件 | 说明 |
| --- | --- |
| `enhance_pattern.bit` / `.hwh` | 位流，WNS **+0.277 ns**，0 失败端点 |
| `pattern_demo.py` | 加载、配置输出时序、切预设、读延迟 |
| `timing_impl.rpt` / `util_impl.rpt` | 实现报告 |

## 复用与差异

这个位流是在 `build/overlay_hdmi_enhance` 的**同一个工程**上，用
`insert_pattern.tcl` 把 `stamp_in` 的输入从 `video/hdmi_in/out_stream` 换成图案发生器后
重新实现得到的——所以内核、配置 GPIO、延迟监视器与 `hdmi_stream_enhance` 完全一致，
只有输入源不同。

## 边界

- 这条通路**没有**验证 HDMI 输入；输入的问题是 EDID/HPD 通了但 TMDS 锁不上，
  排查记录见 `board/hdmi_stream_enhance/README.md`；
- 图案是合成信号，报告与海报里都按"内部图案源"表述。
