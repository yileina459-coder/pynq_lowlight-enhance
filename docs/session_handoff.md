# 当前状态快照（2026-10-22 晚）

给"下次接着干"用的一页纸。细节在各专题文档里，这里只写**现在在哪、下一步是什么**。

---

## 一、现在能跑什么

板上（`/home/xilinx/jupyter_notebooks/hdmi_enh2/`）三类演示，**同一时刻只能有一个进程**
（VDMA 独占）：

```bash
# 停掉一切（必须用 sudo，普通用户杀不掉 root 进程）
echo xilinx | sudo -S sh /home/xilinx/kill_hdmi_demos.sh

# ① 引导演示：8 档 × 25 秒，带解说，循环到 Ctrl-C
sudo env XILINX_XRT=/usr PATH=/usr/local/share/pynq-venv/bin:/usr/bin:/bin HOME=/root \
  /usr/local/share/pynq-venv/bin/python3 hdmi_tour.py \
  --image testcard_640x480.png --roll 45 --hold 25 --rounds 0

# ② 自选图片 + 预设轮播
sudo env ... /usr/local/share/pynq-venv/bin/python3 hdmi_show_image.py \
  --image 你的照片.jpg --roll 45 --cycle 12

# ③ 量化验证"切预设不中断流"（应输出 RESULT: LIVE SWITCH STABLE）
sudo env ... /usr/local/share/pynq-venv/bin/python3 hdmi_live_check.py --cycle 5 --total 60
```

Jupyter（`http://192.168.2.99:9090`，密码 `xilinx`）：`hdmi_panel.ipynb` 有 8 个预设按钮
和图片上传控件。

---

## 二、已解决的硬骨头（都有实测判据）

| 问题 | 根因 | 判据 |
| --- | --- | --- |
| 预设参数不生效 | HLS 把配置锁在流水线 prologue | 生成 RTL 里 `binarize_read_reg_*` |
| 某些预设持续闪烁 | 复位释放跨时钟域 | 改异步断言/同步释放后消失 |
| 切预设黑一下 | 复位中断像素流 → 输出核欠载 | 配置搬进 BRAM 后 741 次写帧 0 卡顿 |
| 画面整体消失（彩条） | 输出 HPD 的 GPIO 方向位是全输入，引脚从未驱动 | `tri=0xFFFFFFFF` 改 0 后恢复 |
| 重启后必变彩条 | `configure()` 重新编程像素时钟 → TMDS 中断 | 现在打印 `pixel clock already correct ... left untouched` |
| 画面水平偏移 ~45 px | 流式流水线延迟像素但不延迟时基 | 互相关测得 43/45/46，等于内核 21–25 拍 + ~20 px |

---

## 三、关键数字（写报告/答辩直接用）

| 项目 | 数值 | 来源 |
| --- | --- | --- |
| 输出分辨率 | 640×480 @60（本板上限） | VDMA 是否消费 + 采集卡 |
| 流水线深度 | **21 拍**（147 ns @142.857 MHz） | HLS 综合报告 `Depth = 21` |
| 片上时间戳读数 | 21–25 拍（含启动偏斜，同轮内恒定） | `axis_cycle_stamp`（只测第一个像素） |
| 切预设期间写帧 | 741 次 / 150 秒 / 25 次切换，**0 次 >60 ms** | `hdmi_live_check.py` |
| DMA 通路逐位一致 | 8 预设各 **0/2764800** 通道 | `board/enhance_dma/` |
| DMA 帧时间 | 15.6 ms（63 fps），PS 基线 3108 ms → **196.7×** | `report/comparison.md` |
| HDMI 位流时序 | WNS **+0.289 ns**，0 失败端点 | `board/hdmi_stream_enhance/timing_impl.rpt` |
| 水平偏移 | 43–46 px（推荐补偿 45） | `tools/diag/measure_capture_offset.py` |
| 纠错记录 | **44 条** | `report/ai_collaboration_log.md` |

---

## 四、剩余工作（按价值排序）

| 优先 | 事项 | 工时 | 阻塞 |
| --- | --- | --- | --- |
| 1 | **SOF/TUSER 帧对齐**：由行计数器在每帧首行产生 TUSER，把 `v_axi4s_vid_out` 的 `C_SOF` 设为 `tuser`，彻底消除 45 px 偏移（现在的 `--roll` 只是补偿） | 1–1.5 h | 需重建位流，注意 module reference 的 XCI 缓存 |
| 2 | **每帧延迟测量**：输入 TLAST 存时间戳、输出 TLAST 相减，替掉现在的单次采样 | 40 min | 同上 |
| 3 | 功耗实测 | 需功率计 | 硬件 |
| 4 | 海报套用 AMD 官方模板 | 20 min | 需模板文件 |

---

## 五、踩过的坑（下次别再踩）

1. **`pkill -f <脚本名>` 会杀掉自己那条 shell**（命令行含同样字符串）→ 用 `tools/board/kill_hdmi_demos.sh`，且必须 sudo。
2. **写 GPIO 数据寄存器 ≠ 改变引脚**——方向寄存器上电全 1（输入），必须先清 `0x04`。
3. **BD 的 module reference 会打包成 XCI + 缓存 DCP**，改 RTL 后必须删 cell 重建，否则网表不变（判据：旧版本特有的信号名还在）。
4. **小存储器会被推断成触发器**，跨时钟变成受时序检查的路径 → 用 `xpm_memory_tdpram`。
5. **HLS 常量下标会把数组折成普通端口**，锁存问题原样回来 → 让下标依赖运行期变量。
6. **脚本一退出画面就变彩条**（VDMA 停供）——这不是故障。
7. **目测不能当测量**：偏移从"30–40 在变"到"恒定 45"的差别，直接改变了结论方向。

---

## 六、文件地图

```
docs/hdmi_status.md            HDMI 全部实测记录（按时间追加，最重要的文档）
docs/submission_checklist.md   提交清单 + 已知限制
report/design_report.md        设计报告（§5.1 真机演示 / §5.2 BRAM 配置）
report/ai_collaboration_log.md 44 条纠错记录
board/hdmi_stream_enhance/     主通路：位流、库、演示、证据、排查脚本、notebook
src/hls/enhance/               内核源码（enhance_body.inc 被两个顶层函数共用）
src/rtl/cfg_bram/              64 位配置存储器（真双口 BRAM）
tools/                         构建/检查/测量/素材生成脚本
```

---

## 七、恢复已验证位流

当前 `board/hdmi_stream_enhance/enhance_hdmi.bit`（WNS +0.289，配置走 BRAM）**已上板验证**。
若要回到"端口配置 + 复位门控"的旧版本：

```bash
git checkout dcfc364 -- board/hdmi_stream_enhance/enhance_hdmi.bit \
                        board/hdmi_stream_enhance/enhance_hdmi.hwh
```

旧版需要 `PULSE_RESET = True`（`hdmi_live.py`）和 `--rebuild-output`（`hdmi_preset_only.py`）。

## 2026-10-23 凌晨：当前状态与下一步

### 交付物状态

- **位流**：`board/hdmi_stream_enhance/enhance_hdmi.bit`（WNS **+0.289 ns**，0 失败端点），
  已在板上验证（overlay 加载、延迟 21、常驻演示正常）。
- **工程树**（`build/overlay_hdmi_enhance/.work/`，未纳入版本控制）：已修复并通过
  `check_bd.tcl` 与综合，可直接重建。
- **仓库与 Gitee 同步**，工作区干净。

### 两个已知问题

| 问题 | 状态 |
|---|---|
| 画面水平偏移 | **根因已确认**：缺 SOF（帧起始），相位每次开机随机（实测 0 / 45 / 89 px）。修复件已就绪（HLS 内核 II=1、228 MHz、接口正确），但**未集成进交付位流** |
| 偶发彩条 | **机制已确认**：像素流中断后采集棒不会自行重新锁定，只有拔插线或重启板子能恢复。运行策略：**启动一次不重启**，参数走 `/tmp/hdmi_{roll,preset,image}.txt` |

### 接着做的话，从这里开始

1. 按 `docs/hdmi_status.md` 里"正确的插入方式"把 `sof_gen` 建在 `/video/hdmi_out` 层级内；
2. 跑 `check_bd.tcl` 确认接口完整，再 `build_bitstream.tcl`（它已内置该检查）；
3. 上板后先 `--roll 0` 观察，再用 `tools/diag/measure_from_screen.py` 从 OBS 截图量偏移；
4. 若偏移在多次重启后稳定在 0±3 px，即证明 SOF 生效，可去掉 `--roll` 补偿路径。

### 注意事项（踩过的坑）

- 改 BD 前先记录要保留的网络端点：删除 cell 会连带删除只连着两个引脚的网络（例如视频复位网）。
- 层级内部网络从顶层 `get_bd_intf_nets` 看不到，必须 `current_bd_instance` 进去操作。
- 引脚级连接会让 PYNQ 的 `.hwh` 解析失败（`MetadataObjectNotFound`），而**位流照样能构建**。
- 每次重启进程都会中断像素流 → 采集棒需要拔插/重启板子；演示时只启动一次。

## 2026-10-23 清晨：交付状态与遗留问题

### 板上现在跑的（已验证 LIVE）

- 位流：`board/hdmi_stream_enhance/enhance_hdmi.bit`（**WNS +0.289 ns**，不含 SOF，
  `git checkout 68372f6` 那一版），实测流是活的（换两张图，屏幕 172,788 像素变化）。
- 常驻演示：`hdmi_resident.py --image testcard_640x480.png --roll 0 --preset clarity`，
  状态文件 `/tmp/hdmi_state.txt`。
- 提亮默认在 **PC 侧**：`page` 曲线（光照平坦化 + 分位拉伸），板上只跑 `clarity`。
  窗口/命令行默认即此路径。

### 三个曾以为的缺陷，结论如下

| 曾怀疑的缺陷 | 结论 | 依据 |
|---|---|---|
| SOF 位流会间歇停流 | **不成立**。是板上同时跑了两个 `hdmi_resident` 争抢 VDMA，加上一次把 `.hwh` 写成 UTF-16 的部署失误 | 单实例 + 正确部署后连续 15 分钟 0 次 `writeframe` 失败 |
| 增益条纹 | **不成立**。两个进程以不同参数交替写同一份配置字，逐像素读参数时帧内参数不稳定就成了列周期条纹 | 单实例下列 std 1.11 / 3.14 / 2.47（噪声量级），无法复现 |
| 偏移随会话变化 | **已解决**。SOF 把相位锚定到帧起始标记 | 三个标记实测 +2 / −2 / +1，平均 **+0.3 像素**（历史值 0 / 45 / 89） |

有一条确实曾是真实回归：latch + II=2 那版内核里增益不生效（`clarity`/`binarize` 正常），
退回 `b36925a` 后恢复。所以交付位流用的是 `b36925a` 内核 + SOF 生成器。

**如果再次遇到"画面冻结 / 配置无反应 / 出现条纹"**，按顺序检查（一分钟内可完成）：
1. `ps -eo args= | grep -c "[h]dmi_resident"` —— 必须只有一个（单实例锁会拦住第二个）；
2. 核对板上 `.bit`/`.hwh` 的 MD5 与仓库一致；
3. 换两张截然不同的图，确认画面真的在跟着变。

### 昨天夜里的方法论收获（写下来避免重犯）

1. **"有画面"≠"流是活的"**。判断存活必须换两张截然不同的图看屏幕是否跟着变；
   日志、单帧画面都会骗人。这个检查当场抓到过一次冻结的 OBS 预览。
2. **脚本说 "connected" 不代表真的连上**。SOF 的 `ap_rst_n` 就是因为取网络失败被静默跳过，
   内核一直复位，表现成"VDMA 不消费"。修法是**回读引脚网络**再确认。
3. **元数据缓存与层级内部网络**：`/video/hdmi_out/frontend` 下的网络从顶层看不到，
   必须 `current_bd_instance` 进去操作；`create_bd_cell` 会留下"半条网络"，
   连接前要把两端都清空。
4. **测量工具的几何假设会过期**。OBS 窗口一动，硬编码的裁剪区就量错东西。
   现在用 `tools/diag/find_video_rect.py`（由红框推导）或差分定位。

### 交接时可以直接用的命令

```powershell
# 看板上状态（谁在显示、什么预设、是否在播放）
ssh xilinx@192.168.2.99 cat /tmp/hdmi_state.txt

# 上传自己的图（默认 PC 侧提亮 + 板上锐化）
tools\board\show_image.ps1 -Image 你的图.jpg

# 播一段动画（GIF/动态 WebP；MP4 需先装 ffmpeg）
tools\board\play_video.ps1 -Video clip.gif -Fps 12

# 量偏移（拍一张桌面截图后）
python tools\diag\measure_offset_screen.py shot.png
```

## 2026-10-23 14:45：视频播放与自动挡位选择（已完成并实测）

上传视频后，程序分析整段、自动选挡，并在板上实时处理播放。详见 `docs/video_playback.md`。

```powershell
tools\board\play_video.ps1 -Video 我的视频.mp4 -Auto clip      # 整段一个挡位（最稳）
tools\board\play_video.ps1 -Video 我的视频.mp4 -Auto adaptive  # 按场景切换挡位
tools\board\play_video.ps1 -Video x -Stop                      # 停止
```

实测（H.264 MP4，24 帧，暗 12 帧 / 亮 12 帧）：分析给出 `reading`(0–11) → `clarity`(12–23)，
边界正好在真实切点；播放 **23.3 fps**（请求 24）、**0 次卡顿**；每个循环只切换 2 次。
三场景片段（暗 8 / 亮 8 / 暗 8）给出 3 段，边界在帧 8 和 16。

**视频格式**：MP4/MOV/MKV 需要 ffmpeg。本机已放在 `.tmp\tools\ffmpeg.exe`（ffmpeg 7.1，
由 `tools/make_video_frames.py` 自动查找：PATH → `.tmp\tools` → `tools\bin`）。
GIF / 动态 WebP 不需要 ffmpeg。

**这次查出的三个真 bug**（都影响可信度，值得记住）：

1. **`play_buf` / `play_cache` 从未定义**——播放每帧抛 `NameError`，被 `except` 吞掉。
   **视频播放此前从未真正工作过**；之前看到的 `playing=24 frames` 只是横幅文字。
   又一次"程序自己说在播"不等于"画面在动"。
2. **每 15 帧卡 2 秒**：播放分支每 15 帧落到主循环的 `time.sleep(args.tick)`，帧率被压到 5 fps 以下；
   改为播放时 50 ms 短休眠后立刻 24 fps。
3. **`-Stop` 一直无效**：`/tmp` 有 sticky 位，普通用户删不掉 root 的文件，`rm -f` 静默失败；
   改为截断。

**分段规则的两次修正**也值得记：用"对称窗口平均"会把 8 帧的短场景抹平（整段塌成一个挡位），
改为"逐帧最优 + 合并过短段"；而"最短段"必须按时长（默认 0.25 s × fps）而不是帧数——
10 帧在 4 fps 下是 2.5 秒（挡掉真场景），在 30 fps 下只有 0.33 秒（挡不住抖动）。
