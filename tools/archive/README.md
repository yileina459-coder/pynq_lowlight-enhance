# archive - 已完成使命的一次性脚本

这些脚本记录了已经解决的问题，或者已经不再适用的实验。**不再维护**，也不保证还能直接运行
（有的依赖当时的环境、临时文件或已经改掉的接口）。保留它们是为了两件事：

1. **可追溯**：报告里提到的某个数字、某张证据图是怎么来的，能顺着脚本找到；
2. **避免重犯**：尤其是那些"看起来在做某件事、其实做出了错误结论"的脚本，配合
   `report/ai_collaboration_log.md` 读更有价值。

| 文件 | 当时的用途 | 为什么归档 |
|---|---|---|
| `check_edid.py` / `dump_edid.py` | 读显示器 EDID，定位 640×480 上限 | 输出分辨率已定案，不再需要逐次检查 |
| `make_edid_640x480.py` / `make_edid_720p_only.py` / `make_hdmi_panel.py` | 制作并替换 EDID，试验 720p | 720p 路线已放弃（见 `docs/hdmi_status.md`） |
| `verify_720p_build.py` | 720p 位流验证 | 同上 |
| `check_stream_widths.py` | 检查 AXI-Stream 位宽连接 | 交接问题已修好，回归由 `check_bd.tcl` 覆盖 |
| `collect_hdmi_evidence.py` / `collect_final_hdmi_evidence.py` | 自动抓取演示截图归档 | 已有更好的 `diag/` 工具与人工归档流程 |
| `reorganise_hdmi_folder.py` | 一次性整理目录 | 那件事已经做完 |
| `report_burst.py` | 连拍分析（找撕裂/跳变） | 被 `diag/watch_loop.py` 与 `diag/check_tearing.py` 取代 |
| `probe_video_gui.py` | 早期 UI 自动化探针 | 已由 `diag/inspect_panel.py` 与 `diag/test_video_gui.py` 取代 |

如果你发现其中某个其实还有用，把它挪回 `tools/diag/` 并更新本表即可。
