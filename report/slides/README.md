# 5 分钟汇报幻灯片

`low_latency_vision_5min.pptx` —— 16:9、9 页、中文，每页都带讲稿与时间标记（备注栏）。

## 时间分配（合计 5:00）

| 页 | 内容 | 时长 | 讲稿位置 |
| --- | --- | --- | --- |
| 1 | 封面：三个数字 | 0:00–0:20 | 备注 1 |
| 2 | 问题：暗光观察卡的是延迟 | 0:20–1:00 | 备注 2 |
| 3 | 方案：零帧缓存直通 + 双通路 | 1:00–1:45 | 备注 3 |
| 4 | 核心算子：59 bit 参数、II=1 | 1:45–2:20 | 备注 4 |
| 5 | 效果：平均亮度 29 → 96/100/104 | 2:20–2:55 | 备注 5 |
| 6 | 正确性：0 容差逐位一致 | 2:55–3:30 | 备注 6 |
| 7 | 性能：196.7×、21 拍 | 3:30–4:05 | 备注 7 |
| 8 | 真机：640×480、切预设不黑屏 | 4:05–4:35 | 备注 8 |
| 9 | 结论 + 已知限制 | 4:35–5:00 | 备注 9 |

超时优先略讲第 4 页的后半段和第 8 页的两个坑。

## 数字出处

| 幻灯片 | 数字 | 文件 |
| --- | --- | --- |
| 1 / 7 / 8 | 21 拍、+0.206 ns、741 次、偏移标定 218（残差 0–1 px） | `board/hdmi_stream_enhance/evidence/final_measurements.json`、`docs/output_offset.md` |
| 7 | 3108.4 / 15.8 ms、196.7× | `board/dma_sobel/metrics_board.csv`、`report/comparison.md` |
| 4 | 3 BRAM / 2 DSP / 1659 LUT / 194.59 MHz | `build/hls/enhance/` 综合报告 |
| 5 | 29 → 96 / 100 / 104 | `report/design_report.md` §5.2、`evidence/presets/brightness_ladder.png` |
| 6 | 9216 拍、0 / 2,764,800 | `board/enhance_dma/metrics_enhance.csv` |

配图全部来自仓库内已有的板上证据（`board/hdmi_stream_enhance/evidence/`、`tuning/source_dark_page.jpg`），没有合成图。

## 重建

```powershell
python report\slides\make_slides.py
```

生成脚本是 `make_slides.py`（python-pptx，纯脚本、可改字后重跑）。
要换汇报人、单位、日期：改脚本里第 1 页的几行文字即可，或者直接在 PowerPoint 里改。

## 现场准备

- 封面未写汇报人与单位，按需补一行。
- 第 8 页的三张图是采集卡实拍（带摩尔纹），答辩时最好再插一段真机录屏或视频链接。
- 备注里标了「如果有人问……」的两处（8 vs 10 个预设、主机 numpy 更快），是被追问时的口径。

---
