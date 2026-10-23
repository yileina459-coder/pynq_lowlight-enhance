# diag - 测量与诊断

平时用不到；出问题时按症状找。

**共同前提**：这些脚本大多要读屏幕截图，所以需要 OBS 预览可见，且画面矩形已用
`find_video_rect.py` 标定过（结果写在 `.tmp/userpic/video_rect.txt`）。

| 症状 | 用哪个 | 看什么 |
|---|---|---|
| 画面有撕裂、几段内容轮流出现 | `check_tearing.py` | 输出 `torn frames: 0` 才算正常 |
| 周期性闪一下 | `watch_loop.py` | 跳变**周期**：等于视频时长是循环点；每 4 帧左右一次是帧缓冲残留 |
| 画面位置偏了 | `measure_offset_screen.py` | 三个标记的平均偏移，`+0.3` 量级才算对齐 |
| 想知道画面区在哪 | `find_video_rect.py` | 打印 `RECT=x0,y0,x1,y1` 并写文件 |
| 面板识别类型不对 | `inspect_panel.py` | 读窗口里的"识别为…"文字 |
| 需要回归测试面板按钮 | `test_video_gui.py` | 自动点击并截图 |
| 想自动调参数 | `tune_dark.py` | 在板上试组合、截图、评分、排序 |
| 标定 `--roll` | `calibrate_roll.py` | 参照图与建议补偿值 |
| 其它截图测量 | `measure_capture_offset.py` / `measure_from_screen.py` / `measure_bars.py` / `measure_residual.py` | 各自的数字定义见文件头 |

**为什么单独放一个目录**：这些脚本会在 `.tmp/` 里生成截图和中间文件，跑起来动静大、和"日常入口"
混在一起容易误用（比如把诊断脚本当成上传脚本跑）。

脚本用 `_repo_root()` 定位仓库根（向上找含 `.git` 的目录），所以放在这一层也能找到 `.tmp/`、
`data/` 和 `tools/` 里的同级模块。
