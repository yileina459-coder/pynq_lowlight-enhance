# sobel — 流式 Sobel 边缘检测核

## 是什么

把 24-bit RGB 像素流逐拍转成边缘图。3×3 窗口，两个方向梯度取绝对值相加：

```text
  -1  0  +1        -1  -2  -1
  -2  0  +2         0   0   0     M = |Gx| + |Gy|，饱和到 0..255
  -1  0  +1        +1  +2  +1
```

输出把 M 复制到 R/G/B 三通道，所以接普通显示器就能直接看到黑白边缘图。

## 接口

| 端口 | 类型 | 说明 |
| --- | --- | --- |
| `s_in` | AXI4-Stream slave | 每拍一个像素，24 bit（`{R,G,B}`），`TLAST` 标记行尾 |
| `s_out` | AXI4-Stream master | 每拍一个像素，侧带信号（last/user/keep/strb）原样透传 |

`ap_ctrl_none`：没有 start/done 握手，数据来了就跑，适合插在视频流水线中间。
因为不消耗 AXI-Lite 寄存器，所以宽度不由寄存器配置，而是由 `TLAST` 自动识别行尾。

## 边界策略（这是和"随便写个 Sobel"最容易对不上的地方）

- **水平方向**：行首的窗口做复制，即三列取 `(max(c-2,0), max(c-1,0), c)`。
  因此第 c 个输出像素对应输入的第 c-1 列（整体左移一列，宽度不变）。
- **垂直方向**：三行来自三个行缓冲，即 `(r-2, r-1, r)`。上电后前两行的行缓冲是 0；
  视频连续流过时，行缓冲里是**上一帧**的最后两行 —— 这对连续视频是正确的，但意味着
  "单张图片喂进去比对"时顶部两行会和软件参考不一致。比对脚本因此提供
  `--border wrap` 和 `--ignore-rows N` 两种口径，见 `sim/sobel/golden_sobel.py`。
- **亮度**：`Y = (77R + 150G + 29B) >> 8`，整数运算，硬件与软件参考逐位一致。

## 已验证结果（2026.1，`xc7z020clg400-1`，10 ns 约束）

| 项目 | 结果 |
| --- | --- |
| C 仿真 | `SOBEL TB PASS`，9216 拍进出，0 误差，侧带信号无损坏 |
| 吞吐 | II = 1（每时钟 1 像素），循环深度 10 |
| 时序 | 估计 Fmax ≈ **141.9 MHz**（720p60 只需 74.25 MHz 像素时钟） |
| 资源 | BRAM 3（1%）、DSP 2（~0%）、FF 583、LUT 809（1%） |
| 导出 | `export/sobel.zip` 可直接在 Vivado 里 `Add IP` |

资源这么省的原因是三个行缓冲只占 3 个 18K BRAM（1920×8bit 一个），梯度用 2 个 DSP 做乘加。

## 怎么跑

```bat
tools\env\vitis_hls.bat -f build\hls\sobel\run_hls.tcl
```

产物：`build/hls/sobel/proj/`（工程）、`build/hls/sobel/reports/csynth.rpt`（报告）、
`build/hls/sobel/export/sobel.zip`（IP 包）。

## 软件黄金参考

```bash
python sim/sobel/golden_sobel.py --generate-test-image data/images/test_720p.png
python sim/sobel/golden_sobel.py --input data/images/test_720p.png \
    --reference data/reference/sobel_720p.png \
    --preview data/reference/sobel_720p_preview.png --border wrap
python sim/sobel/golden_sobel.py --compare <板上抓的帧>.png \
    --reference data/reference/sobel_720p.png --ignore-rows 2
```

比对脚本要求 **bit-exact**（0 个通道不一致），不放宽到 PSNR 阈值，这样任何一处
口径不一致（亮度公式、边界、饱和方式）都会立刻暴露。

## 已知限制

- 只支持 RGB 输入；色度空间转换是另一个算子，放在它前面。
- 行宽超过 `SOBEL_MAX_W`（默认 1920）会不正确；改这个宏即可，代价是 BRAM 数量。
- 没有可编程阈值（阈值化会破坏与软件参考的逐位一致性，留作可选的后续参数）。
