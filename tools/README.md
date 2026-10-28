# tools 目录地图

按"什么时候会用到"分组。日常只需要记住前两行。

## 一、日常入口

| 位置 | 作用 |
|---|---|
| `board/upload_panel.ps1` | **统一上传面板**（图片 / 视频）。双击根目录的 `上传到开发板.bat` 打开它 |
| `board/show_image.ps1` | 命令行上传一张图并显示 |
| `board/play_video.ps1` | 命令行播放一段视频（`-Auto clip` / `-Auto adaptive` / `-Preset`） |
| `board/reset_board.ps1` | 一键恢复干净状态（停播放、清排帧、设图片和挡位、回读确认） |
| `board/ensure_demo.ps1` | 检查板上的演示进程，没运行就启动（面板打开时自动调用），启动后自动标定画面偏移 |
| `board/status.sh` | 一条命令看板上全部状态（进程、状态文件、控制文件、排程、日志、写帧失败数） |
| `board/fix_offset.ps1` | **画面水平偏移**：自动测量 + 写补偿 + 验残差（`-Measure` 只量不改）。演示重启后跑一次 |

## 二、核心管线（会被上面的入口调用）

| 文件 | 作用 |
|---|---|
| `board/align_output.py` | 画面偏移的测量与补偿本体（八色彩条 + OBS 预览 + 色相判读），被 `board/fix_offset.ps1` 调用 |
| `prepare_image.py` | 图片转 640×480、比例适配、PC 侧提亮曲线 |
| `preview_enhance.py` | 内核的精确复现，无需上板就能看到处理效果 |
| `make_video_frames.py` | 视频解码成帧序列（MP4 走 ffmpeg，GIF/WebP 走 Pillow） |
| `analyze_video.py` | 逐帧给每个挡位打分，选出"整段一个挡位"或"按场景切换"的排程 |
| `score_capture.py` | 可读性评分（对比度、边缘、过曝、平均亮度） |
| `rank_tones.py` | 离线比较各条提亮曲线，用同一套评分 |
| `make_frame.py` / `make_testcard.py` | 生成测试图 |

## 三、仓库自检

| 文件 | 作用 |
|---|---|
| `check_consistency.py` | 文档与代码的关键数字/路径是否对得上（`--strict` 用于提交前） |
| `check_presets.py` | 板上与 PC 侧的挡位表是否一致 |
| `check_frame.py` | 检查 640×480 帧的格式与大小 |
| `check_sof_gen.py` | SOF 生成器的行为检查 |

## 四、诊断（`diag/`，出问题时才用）

| 文件 | 作用 |
|---|---|
| `check_tearing.py` | 用逐帧黑白交替的片段检测撕裂 / 旧帧残留 |
| `watch_loop.py` | 连续采样一个循环，找闪烁、跳变及其周期 |
| `find_video_rect.py` | 从 OBS 红框定位画面矩形（写 `.tmp/userpic/video_rect.txt`） |
| `measure_offset_screen.py` | 用标尺图量画面水平偏移 |
| `measure_capture_offset.py` / `measure_from_screen.py` / `measure_bars.py` | 其它截图测量 |
| `measure_residual.py` | 测量处理后的残留差异 |
| `calibrate_roll.py` | 标定 `--roll` 补偿值 |
| `tune_dark.py` | 自动在板上试参数、截图、评分、排序 |
| `inspect_panel.py` | 用 UI Automation 读上传面板里的文字（验证"识别为图片/视频"） |
| `test_video_gui.py` | 自动点击面板按钮并截图（UI 回归用） |

## 五、归档（`archive/`，已完成使命）

早期 HDMI 打通、720p 试验、EDID 生成、证据收集等一次性脚本。保留是为了可追溯，**不再维护**，
也不保证还能直接运行。见 `archive/README.md`。

## 六、注意事项

- **脚本定位仓库根**：`tools/diag/` 与 `tools/archive/` 下的脚本用 `_repo_root()` 向上查找含 `.git`
  的目录来确定仓库根，不使用固定的 `parent.parent`。这样脚本所在层级调整后，仍能定位 `.tmp/`、
  `data/` 与 `tools/` 下的资源。新增脚本应沿用该写法；写死层级会在移动脚本后失效。
