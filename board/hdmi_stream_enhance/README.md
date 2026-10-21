# enhance_hdmi — 真机 HDMI 增强通路

```
PS 写一帧到 DDR ──► VDMA MM2S ──► stamp_in ──► enhance ──► stamp_out
                                                              │
                                    pixel_unpack ◄────────────┘
                                          │
                                    v_axi4s_vid_out ──► rgb2dvi ──► HDMI OUT
                                                                      │
                                                                HDMI 采集卡 ──► OBS
```

**内核在像素通路上**，一帧数据从 VDMA 出发、穿过 `enhance_stream`、直接进视频输出，
全程在 PL 里，PS 只负责送帧和改配置。

## 为什么视频源是 VDMA 而不是 HDMI IN

板上实测（2026-10-22）：这块 PYNQ-Z2 的 HDMI **输出**只有 640×480 能工作，
720p / 1080p 下一帧都不会被消费、不产生 TMDS：

| 输出模式 | 像素时钟 | `writeframe` 是否返回 | 采集卡 |
| --- | --- | --- | --- |
| 640×480 | 25.175 MHz | 立即返回 | 有画面 |
| 800×600 | 40 MHz | 阻塞 | 无信号 |
| 1280×720 | 74.25 MHz | 阻塞 | 无信号 |
| 1920×1080 | 148.5 MHz | 阻塞 | 无信号 |

（判据是 `writeframe()` 只在 VDMA 完成一次帧传输后才返回，所以不依赖采集卡。
原厂 `base.bit` 行为相同，因此这是板子的物理上限——PYNQ-Z2 的 HDMI 口无缓冲、直连 PL。）

而 **HDMI 输入无法工作在 640×480**：`dvi2rgb` 的 `kClkRange` 只接受 1/2/3，
25.175 MHz 需要 5 档才能让 VCO 落在 600–1200 MHz。

两个限制叠加的结果是"直通不可行"，所以帧源改成 VDMA，**内核仍然在真实像素通路上**。

## 预设切换与内核复位

内核是自由运行的（`ap_ctrl_none`），HLS 把配置输入当作循环不变量、在流水线
prologue 里锁存一次：

```
binarize_read_reg_1446 <= binarize;      // 只在 prologue 采一次
```

所以 6 个参数（`knee/thresh/binarize/invert/mono/split_x`）在运行期改不动，
只有 `clarity/gain_lo/gain_hi` 是组合直连的。

修法：`src/rtl/enh_rst_gate/enh_rst_gate.v` 让 PS 用配置字的空闲位 `cfg_hi[31]`
复位内核，`write_preset()` 按"参数就位 → 断言复位 → 释放"的顺序脉冲一次，
prologue 就会用新值重新采样。

**代价**：每次换预设的当帧会花屏一帧（line buffer 被清空）。彻底做法是把这 6 个
参数放进 BRAM，属优化项。

## 真机证据

`evidence/` 里的四张采集卡截图，来自同一次连续运行、四个不同预设：

| 文件 | 画面 |
| --- | --- |
| `hdmi_preset_02_pass.png` | 平滑渐变 + 灰带 + 黑色文字条 + 三色块，即原始测试图 |
| `hdmi_preset_03_binarize.png` | 大面积黑 + 底部白带（阈值切分） |
| `hdmi_preset_01_document.png` | 暗部抬起、中段变亮 |
| `hdmi_preset_04_high_gain.png` | 过曝、高对比、色块饱和 |

四张互不相同，与四个预设的数学效果一致。

## 文件

| 文件 | 作用 |
| --- | --- |
| `enhance_hdmi.bit` / `.hwh` | 位流（WNS +0.370 ns） |
| `hdmi_solid.py` | 最小验证：一帧纯色，判断整条输出通路是否工作 |
| `hdmi_vdma_demo.py` | **主演示**：测试图穿过内核 + 预设循环 + 每帧写帧耗时 |
| `hdmi_preset_stream.py` | 持续推帧 + 定时切预设（用于观察预设效果） |
| `hdmi_ab.py` | 两档预设 A/B，打印配置写入与回读 |
| `hdmi_first_preset.py` | 先写配置再推帧（验证 prologue 采样时机） |
| `hdmi_two_phase.py` | 两阶段诊断：先变内容、再变配置 |
| `hdmi_content_flip.py` | 只变内容，判断画面是否实时刷新 |
| `hdmi_live.py` | 预设表、`pack()`、`write_preset()`（含复位脉冲） |
| `hdmi_in_check.py` | 正确读取 HDMI 输入模式（`_capture` 才报 "No incoming video signal"） |
| `hdmi_clk_probe.py` | `axi_dynclk` 寄存器与锁定状态 |
| `timing_impl.rpt` / `util_impl.rpt` | 实现报告 |

## 跑

板上（root + PYNQ venv）：

```bash
cd /home/xilinx/jupyter_notebooks/hdmi_enh2

# 最小验证：一帧纯色
sudo env XILINX_XRT=/usr PATH=/usr/local/share/pynq-venv/bin:/usr/bin:/bin HOME=/root \
  /usr/local/share/pynq-venv/bin/python3 hdmi_solid.py --colour 0,200,0 --hold 60

# 主演示：测试图 + 7 档预设循环
sudo env XILINX_XRT=/usr PATH=/usr/local/share/pynq-venv/bin:/usr/bin:/bin HOME=/root \
  /usr/local/share/pynq-venv/bin/python3 hdmi_vdma_demo.py --cycle 8
```

预期输出：

```
hdmi_out running at 640x480
test image (480, 640, 3), mean 124.0
[...] preset clarity   writeframe 6.5 ms  latency 21 pixel clocks
[...] preset document  writeframe 6.4 ms  latency 21 pixel clocks
```

## 注意事项

1. **同时只能有一个进程**占着 overlay/VDMA，否则互相抢占，表现是"跑通了又变彩条"；
   测试前先 `ps aux | grep hdmi_`。
2. 每次加载位流会把 HDMI 输入的 HPD 清零，Windows 会认为显示器被拔掉；
   需要显示 2 号屏时用 `hdmi_restore_hpd.py`。
3. 进程退出后 VDMA 停止供帧，采集卡会回到兜底彩条——这是正常的，不是故障。

## 采集序列（2026-10-21 晚）

`evidence/` 里的 `hdmi_capture_*.png` 来自同一次连续运行，按画面特征命名：

| 文件 | 画面 |
| --- | --- |
| `hdmi_capture_plain.png` | 原始状态 |
| `hdmi_capture_split.png` | **垂直分屏**（左 1/3 原样） |
| `hdmi_capture_binarize.png` | **硬阈值**（黑底 + 白带） |
| `hdmi_capture_sharpened.png` | 高对比/过锐 |
| `hdmi_capture_glitch.png` | 换预设当帧的花屏（预期代价） |
| `hdmi_presets_2x2.png` | 四张拼图，海报配图 |

**闪烁说明**：换预设时内核被复位，line buffer 清空 → 当帧花屏，下一帧恢复。
这是 `enh_rst_gate` 方案的已知代价。

## 复位门控（2026-10-22 更新）

预设切换靠 `enh_rst_bridge` 复位内核，让 HLS 的流水线 prologue 重新采样配置。
实现是**异步断言 / 同步释放**：`cfg_hi[31]` 在 100 MHz PS 域，释放经内核 142.857 MHz
时钟两级同步后才送到 `ap_rst_n`。

第一版是纯组合的 `ap_rst_n = aresetn & ~cfg_hi[31]`，复位释放落在任意时钟相位上，
板上表现为**某些预设持续闪烁**（内核带着错乱的 line-buffer 指针退出复位）。
改成复位桥后 `writeframe` 稳定 6.5 ms、延迟恒定 21 拍。

注意：`cdc.xdc` 里对这条路径设了 false path——**异步断言本来就不该做时序检查**，
只有释放需要同步，而同步在桥内部完成。
