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
| 水平偏移 | 43–46 px（推荐补偿 45） | `tools/measure_capture_offset.py` |
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
