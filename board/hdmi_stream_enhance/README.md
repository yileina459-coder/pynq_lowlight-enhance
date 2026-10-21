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

## 用自己的图片（2026-10-22 新增）

不用再盯着测试图了：随便一张照片都能显示在这块屏幕上，并且照样穿过增强内核。

**方式一：Jupyter 上传（最省事）**

打开 `notebooks/hdmi_panel.ipynb` → 跑完前面的单元格 → 在"显示你自己的图片"那格点
**选择图片**，选一张 PNG/JPEG 即可。脚本会自动按比例缩放并加黑边（letterbox），
不裁掉内容。

**方式二：电脑转码 + 板上显示**

```powershell
# 电脑上（任何 Pillow 能读的格式）
python tools\make_frame.py photo.jpg --out frame.bin          # 640x480 黑边
python tools\make_frame.py photo.jpg --out frame.bin --fit crop   # 裁满屏
python tools\check_frame.py                                   # 校验格式与通道顺序
scp frame.bin xilinx@192.168.2.99:/home/xilinx/
```

```bash
# 板上
sudo env XILINX_XRT=/usr PATH=/usr/local/share/pynq-venv/bin:/usr/bin:/bin HOME=/root \
  /usr/local/share/pynq-venv/bin/python3 hdmi_show_image.py --raw frame.bin --preset document
# 想让它自己轮播 8 档预设：
  ... hdmi_show_image.py --raw frame.bin --cycle 8 --hold 600
```

**为什么在电脑上转码**：PYNQ 3.1.1 不一定带 Pillow，而且解码图片属于 CPU 活——
这条通路的卖点恰恰是"像素由 PL 处理"。转成裸 RGB 后板上只是 `numpy.frombuffer`，
格式一眼可见。

`tools/check_frame.py` 会验证 PC 侧和板侧的测试图**逐字节一致**、通道是 R,G,B 顺序、
尺寸正好 640×480×3——红蓝互换或上下颠倒这种问题否则能一路带到答辩现场。

## 目录结构

```
board/hdmi_stream_enhance/
├── enhance_hdmi.bit / .hwh  位流与硬件描述（WNS +0.171 ns）
├── timing_impl.rpt / util_impl.rpt
├── base.xsa                 导出给 Vitis 的设计
├── hdmi_live.py             共享库：预设表、pack()、write_preset()（含复位脉冲）
├── hdmi_preset_only.py      **主演示**：写一帧 → 每次切预设后重建输出链路
├── hdmi_vdma_demo.py        备选演示：每次切预设都重写一帧
├── hdmi_restore_hpd.py      工具：加载位流后恢复 Windows 的 2 号屏
├── evidence/                采集卡截图（按画面特征命名）+ 2×2 拼图
├── diagnostics/             21 个排查脚本，每个对应一个具体问题
└── notebooks/               Jupyter 版验证与演示（hdmi_panel.ipynb = 点按钮切预设）
```

## 跑

板上（root + PYNQ venv）：

**方式一：Jupyter 面板（推荐）**

打开 `notebooks/hdmi_panel.ipynb` → Run All → 出现 **8 个按钮**，点哪个就切到哪个预设，
下方实时显示流水线延迟；最后一格是自动循环（每档 15 秒），适合录屏。

**方式二：命令行**

```bash
cd /home/xilinx/jupyter_notebooks/hdmi_enh2

# 主演示：640×480 测试图 + 8 档预设循环，每次切换重建输出链路
sudo env XILINX_XRT=/usr PATH=/usr/local/share/pynq-venv/bin:/usr/bin:/bin HOME=/root \
  /usr/local/share/pynq-venv/bin/python3 hdmi_preset_only.py --cycle 15
```

预期输出：

```
hdmi_out running at 640x480
test image written once (8.6 ms); no further DDR writes from here on
[...] preset document  latency 21 (output path restarted)
[...] preset binarize  latency 21 (output path restarted)
```

排查脚本在 `diagnostics/`，**从本目录运行**（它们 `import hdmi_live`，工作目录要在上一层）：

```bash
cd /home/xilinx/jupyter_notebooks/hdmi_enh2
sudo env ... /usr/local/share/pynq-venv/bin/python3 diagnostics/hdmi_probe_buffers.py
```

## diagnostics/ 索引（按"回答什么问题"排列）

| 脚本 | 回答的问题 |
| --- | --- |
| `hdmi_enhance.py` | overlay 能否加载、`video` 是否绑定、配置寄存器能否读写 |
| `hdmi_solid.py` / `hdmi_static_frame.py` | 输出通路是否工作（纯色 / 静态图） |
| `hdmi_probe_buffers.py` | VDMA 的帧缓冲里到底装着什么（读回 numpy 统计） |
| `hdmi_in_check.py` | HDMI 输入到底有没有信号（`_capture` 才会报 "No incoming video signal"） |
| `hdmi_clk_probe.py` | `axi_dynclk` 是否锁定、寄存器读数 |
| `hdmi_stock_check.py` / `hdmi_out_lowclk.py` | 原厂位流能否出图、各分辨率的输出上限 |
| `hdmi_hpd_probe.py` / `hdmi_hpd_out_test.py` / `hdmi_restore_hpd.py` | HPD 与显示器枚举 |
| `hdmi_follow.py` / `hdmi_presets.py` / `hdmi_passthrough.py` | 跟随输入模式、按档位跑、直通尝试 |
| `hdmi_ab.py` / `hdmi_live_only.py` / `hdmi_first_preset.py` | 配置写入与采样时机（prologue 锁存） |
| `hdmi_two_phase.py` / `hdmi_content_flip.py` / `hdmi_one_preset.py` | 分离"内容变化"与"配置变化" |
| `hdmi_preset_stream.py` / `hdmi_smooth_demo.py` | 不同节奏/不同画面的预设循环 |
| `hdmi_after_fix.py` | 给 `kClkRange` 修复后做输入检测的那一版 |

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

## 演示主脚本与闪烁排查结论（2026-10-22 定稿）

**演示用 `hdmi_preset_only.py`**：写一帧 → 每次切预设后重启输出链路 → 稳定出图。

闪烁排查中排除掉的假设（都留有客观判据，见 `docs/hdmi_status.md`）：
帧缓冲黑帧（读回 4 块缓冲均为正常图像）、输出链路不稳（静态灰面 85 秒稳定）、
OBS 缩放锯齿（改 1:1 后仍闪）、写 DDR 撕裂（只写一帧仍闪）。

**根因**：切预设要复位内核（HLS 把配置锁在流水线 prologue），复位会截断像素流，
`v_axi4s_vid_out` 随之欠载，采集卡只能自行重锁——这个过程看起来就是"图像 ↔ 黑"交替。

**修法**：复位之后立刻 `stop() / configure() / start()` 并重新填满 4 块帧缓冲，
让输出链路从确定状态重新开始，而不是靠采集卡自己恢复。

## 最终采集序列（稳定版演示）

| 文件 | 画面 |
| --- | --- |
| `hdmi_final_a_plain.png` | 干净原图 |
| `hdmi_final_b_brighter.png` | 提亮 + 竖纹 |
| `hdmi_final_c_dark.png` | 暗场 |
| `hdmi_final_d_desaturated.png` | 去色/反相倾向 |
| `hdmi_final_e_inverted.png` | 暗场 + 亮文字条 |
| `hdmi_final_f_split.png` | **垂直分屏：左原样、右处理** |
| `hdmi_presets_2x2.png` | 四张拼图（海报配图，含分屏那张） |

`hdmi_final_f_split.png` 是最强的单帧证据：同一帧内同时有原样区与处理区，说明内核在实时
处理像素流。旧的一组（`hdmi_capture_*`）保留作排查记录。

## 2026-10-22 凌晨：切换不再闪（配置走 BRAM）

位流已更新为 **memory-configured kernel**：`enhance_stream_cfg` 每像素从 BRAM 读一次
64 位配置，切预设只是写一次 GPIO，不复位、不中断像素流。WNS **+0.289 ns**。

实测（`hdmi_live_check.py`，150 秒、25 次切换、741 次写帧）：

```
write time     : min 2.1 ms, median 2.2 ms, max 17.1 ms
stalls > 60 ms: 0
latency values : [21]
RESULT: LIVE SWITCH STABLE
```

**主演示现在直接跑实时切换**：

```bash
sudo env ... python3 hdmi_preset_only.py --cycle 15      # 8 档循环，无黑屏
sudo env ... python3 hdmi_show_image.py --raw frame.bin --cycle 8   # 自己的图片
```

旧位流仍可用 `--rebuild-output` 复现"复位 + 重建输出链路"的老路径（会有一次短暂黑屏），
仅作对比用。

新增文件：`hdmi_show_image.py`（显示自己的图片）、`hdmi_live_check.py`（量化验证切换
不中断流）、`diagnostics/hdmi_image_debug.py` / `hdmi_order_test.py`（排查用的分步计时）。
