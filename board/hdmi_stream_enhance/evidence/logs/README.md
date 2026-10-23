# 板端日志存档（2026-10-22）

这些是从板上 `/tmp/*.log` 直接拷下来的运行日志。放在这里的原因是：**它们证明了文档里的数字**，
而且 `/tmp` 会在重启后清空。文件名按"证明什么"重命名过，括号里是板上的原始文件名。

| 文件 | 证明了什么 | 对应文档 |
| --- | --- | --- |
| `live_switch_150s.log`（`lc_long.log`） | 150 秒、25 次预设切换、**741 次写帧、0 次超过 60 ms**、延迟读数恒定 —— `RESULT: LIVE SWITCH STABLE` | `docs/hdmi_status.md`、报告 §5.2 |
| `live_switch_30s.log`（`lc4.log`） | 同一测试的短版本（30 秒），用于快速回归 | 同上 |
| `startup_reuse_clock_a.log` / `_b.log`（`runA/runB`） | 连续两次启动都走"复用像素时钟"路径：`pixel clock already correct (640x480 locked), left untouched`，且帧被正常消费（`latency 24`） | `docs/hdmi_status.md` 2026-10-22 晚章节 |
| `startup_program_clock.log`（`run1.log`） | 对照组：模式文件被清空时走 `pixel clock programmed`（会中断 TMDS） | 同上 |
| `guided_tour_loop.log`（`tour_loop.log`） | 8 档 × 25 秒的循环引导演示，`--roll 45`、每档延迟读数 | `board/hdmi_stream_enhance/README.md` |
| `guided_tour_30s.log`（`tour_long.log`） | 8 档 × 30 秒的完整一轮 | 同上 |
| `ruler_pattern.log`（`ruler2.log`） | 标尺图案显示，用于从截图量水平偏移 | `tools/diag/measure_capture_offset.py` |
| `stock_overlay_control.log`（`stock640.log`） | 对照实验：**原厂 `base.bit` 在 640×480 下同样出不了画面**，说明彩条不是我们设计的问题 | `docs/hdmi_status.md` |
| `own_image_demo.log`（`photo_demo.log`） | 显示自己的图片 + 预设轮播（`1600x900 -> 640x360 centred (letterboxed)`） | `board/.../README.md` |

**注意**：日志里的时间戳是板子的时钟（UTC），与电脑时间不同步，不要拿去和截图时间对齐。
