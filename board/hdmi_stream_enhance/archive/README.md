# archive - 被取代的板上入口

这些是早期为不同演示场景各写一个入口时留下的脚本。它们**能跑，但不再是入口**：
现在所有图片/视频都走 `tools/board/upload_panel.ps1`（双击根目录的 `upload_to_board.bat`），
它调用 `show_image.ps1` / `play_video.ps1`，播放与切图都在 `hdmi_resident.py` 一个进程里完成
——这是唯一不会打断像素流的做法。

| 文件 | 当时的用途 | 现在用什么代替 |
|---|---|---|
| `hdmi_show_image.py` | 显示一张图（独立进程） | `tools/board/show_image.ps1` + 常驻演示 |
| `hdmi_player.py` | 播放帧序列（独立进程） | `tools/board/play_video.ps1`（常驻演示的播放模式） |
| `hdmi_ruler.py` | 显示标尺图并固定 roll | `show_image.ps1 -Image data/images/ruler_640x480.png` |
| `hdmi_tour.py` | 自动轮播所有挡位 | 面板里手动选挡，或 `hdmi_preset_only.py` |
| `hdmi_preset_only.py` | 只切挡位不换图 | `/tmp/hdmi_preset.txt`（常驻演示会读） |
| `hdmi_vdma_demo.py` | VDMA 最小示例 | `hdmi_resident.py` |
| `hdmi_live_check.py` | 早期自检脚本 | `tools/board/status.sh` |
| `hdmi_restore_hpd.py` | 恢复 HPD 电平 | 已并入 `hdmi_live.py` |

**为什么保留**：它们记录了"每换一个场景就起一个新进程"这条错路——每次重启进程都会打断像素流，
采集卡随后丢锁，只能拔插 HDMI 或重启板子。`docs/hdmi_status.md` 里反复出现的"彩条"现象就是它。
