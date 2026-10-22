# 上传你自己的图片

一条命令，把电脑上任意一张图放到板子的 HDMI 输出上。

## 用法

```powershell
cd C:\Users\79171\Desktop\FPGA
powershell -NoProfile -ExecutionPolicy Bypass -File tools\board\show_image.ps1 -Image C:\Users\79171\Desktop\你的照片.jpg
```

预期输出：

```
source 4032x3024 -> 640x480 (letterbox)
wrote C:\Users\79171\Desktop\FPGA\.tmp\upload\mine_221308_640x480.png  mean=118.4  min=0  max=255
OK - the board is now showing /tmp/hdmi_uploads/mine_221308_640x480.png
  image=/tmp/hdmi_uploads/mine_221308_640x480.png
  roll=0
  preset=pass
  sof=None
  mode=640x480
  updated=2025-05-05 23:51:21
```

看到 `OK - the board is now showing ...` 就是成功了，屏幕上的画面会在 1～3 秒内换掉。

## 接口比例（`-Fit`）

| 取值 | 效果 | 适合 |
|---|---|---|
| `letterbox`（默认） | 保持比例，四周用 `-Background` 填边 | 文档、表格、整页扫描 |
| `crop` | 保持比例填满，裁掉溢出部分 | 照片、想填满整屏 |
| `stretch` | 直接拉伸填满 | 不在乎变形 |

```powershell
# 裁切填满，白边用浅灰
... -Image photo.jpg -Fit crop
# 同时切换增强预设
... -Image scan.png -Fit letterbox -Preset threshold
```

`-Background 0..255` 只对 `letterbox` 有效，默认 0（黑色）。

支持的输入格式：Pillow 能读的都行——JPG / PNG / BMP / WEBP / TIFF / GIF。手机拍的竖图会按 EXIF
方向自动转正。**HEIC（iPhone 默认格式）不支持**，先导出成 JPG。

## 为什么不用重启

板上的常驻演示 `hdmi_resident.py` **独占 VDMA**，而且这个 USB 采集棒有个特性：**像素流一旦中断
就不会自己重新锁定**，只能靠拔插 HDMI 线或重启板子恢复。所以换图不能重启进程，而是走文件接口：

| 文件（板上） | 内容 |
|---|---|
| `/tmp/hdmi_image.txt` | 要显示的图片路径（PNG/JPEG） |
| `/tmp/hdmi_roll.txt` | 水平补偿像素数 |
| `/tmp/hdmi_preset.txt` | 增强预设（`pass` / `threshold` / `sobel` / …） |
| `/tmp/hdmi_sof.txt` | SOF 生成开关（`0`/`1`） |
| `/tmp/hdmi_state.txt` | **演示回报的当前状态**（只读） |

这些文件由常驻进程在启动时设成 `666`，上传目录 `/tmp/hdmi_uploads` 设成 `777`，所以 PC 端
**全程不需要 sudo**，重启后也自动生效。

## 排查

| 现象 | 原因与处理 |
|---|---|
| `the resident demo is not running` | 演示没起来。按提示启动一次（只启一次，之后别重启） |
| 状态文件里还是旧图 | 等 3 秒再看；`ssh xilinx@192.168.2.99 cat /tmp/hdmi_state.txt` |
| 屏幕上是彩条 | 采集棒丢了锁定：**拔插 HDMI 线**或重启板子，然后重新启动演示 |
| 图显示为全黑 | 源图太暗；`prepare_image.py` 会打印 `mean=` 提示 |
| 画面偏左/偏右 | 这是随会话变化的相位（见 `docs/hdmi_status.md`）：用 `tools/measure_bars.py` 量，再写 `--roll` |

## 相关文件

- `tools/board/show_image.ps1` —— 一键上传（转换 → 传输 → 切换 → 校验）
- `tools/prepare_image.py` —— 图片转 640×480 PNG，可单独用来预览效果
- `board/hdmi_stream_enhance/hdmi_resident.py` —— 板上常驻演示
