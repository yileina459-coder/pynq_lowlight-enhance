# HDMI 流式 Sobel（主展示形态）

这一版把 PYNQ 官方 base overlay 在 Vivado 2026.1 里重建，并把 Sobel 核插在
`pixel_pack` 和 `pixel_unpack` 之间——视频流**不经过帧缓冲**，延迟大约一行。

```text
HDMI In ─ dvi2rgb ─ v_vid_in_axi4s ─ color_convert ─ pixel_pack ─┐
                                                                │
                                                        sobel_0（本作品）
                                                                │
HDMI Out ─ rgb2dvi ─ v_axi4s_vid_out ─ color_convert ─ pixel_unpack ┘
```

## 文件

| 文件 | 作用 |
| --- | --- |
| `sobel_hdmi.bit` / `sobel_hdmi.hwh` | 位流与握手文件（由 `build/overlay_hdmi/build.bat` 生成） |
| `hdmi_sobel.py` | 加载 overlay、配置输入输出、启动管线 |
| `demo.ipynb` | 同上，Notebook 版本 |

## 怎么跑

板上目录（例如 `/home/xilinx/jupyter_notebooks/hdmi_stream/`）里放两个
`sobel_hdmi.*` 文件和脚本，然后：

```bash
python3 hdmi_sobel.py --seconds 10
```

期望输出：

```text
loading sobel_hdmi.bit
IPs in design: 4x
configuring HDMI input
detected input mode: 1280x720 @ 60.00 Hz, pixel clock 74.25 MHz
configuring HDMI output
pipeline running - HDMI OUT should now show the Sobel edge image
RESULT: OK
```

- **输入源**：笔记本的 HDMI 输出（或相机）接到板子的 HDMI IN。
- **输出**：接显示器/电视；没有显示器就用 HDMI 采集卡（几十元）在笔记本上看。

## 怎么确认位流里真的插了算子

不用上板也能查。位流的块设计文件里能看到数据通路的连接：

```powershell
$bd = "build\overlay_hdmi\.work\tree\boards\Pynq-Z2\base\base\base.srcs\sources_1\bd\base\base.bd"
Select-String -Path $bd -Pattern 'sobel_0_s_out|video_out_stream' -Context 0,2
```

本机实测输出（即 `board/hdmi_stream/sobel_hdmi.bit` 对应的连接）：

```text
"video_out_stream" : { "interface_ports": [ "sobel_0/s_in", "video/out_stream" ] }
"sobel_0_s_out"    : { "interface_ports": [ "sobel_0/s_out", "video/in_stream" ] }
```

也就是 `HDMI IN → video/out_stream → sobel_0 → video/in_stream → HDMI OUT`，
并且 `axi_vdma/S_AXIS_S2MM` 上**已经没有**任何流网络（帧缓冲环回被切断）。
`sobel_0/ap_clk` 接的是 `ps7_0_FCLK_CLK1`（142.857 MHz），与 `.hwh` 里 `ap_clk` 报告一致。

## 这一版能验证什么、不能验证什么

能验证：

- 2026.1 生成的 overlay 能被板上的 PYNQ 镜像正常加载（**这是整个 HDMI 路线最大的版本风险**）
- HDMI 输入能锁定信号并报出分辨率/像素时钟
- 输出管线启动无异常

不能验证（需要显示器或采集卡）：

- 屏幕上到底有没有边缘图、有没有撕裂/花屏

因为视频流绕过了 VDMA，PS 侧没有可回读的帧，所以 **`hdmi_in.readframe()` 在这个
overlay 上不可用** —— 这是刻意的取舍：要低延迟直通，就不要帧缓冲。

## 与 DMA 版的关系

| | DMA 版（`board/dma_sobel/`） | HDMI 版（本目录） |
| --- | --- | --- |
| 用途 | 功能正确性的**数字证据**（与黄金参考逐位比对） | 作品的**展示形态**（实时视频） |
| 需要显示器 | 不需要 | 需要（或采集卡） |
| 延迟 | 一次 DMA 往返 + 每行一次传输开销 | 约一行 |
| 测出的帧率 | 偏低（受 DMA 每次传输开销拖累） | 真实的流式帧率 |

两个版本用的是**同一个 HLS 核**，只是打包时的时钟约束不同（DMA 版 100 MHz，
HDMI 版按 142.86 MHz 的 `clk_142M` 收敛）。

## 常见问题

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| `no 'video' hierarchy` | bit/hwh 不配套，或用了别的 overlay | 确认两个文件都来自同一次构建 |
| `no HDMI input signal detected` | 源没接、源没输出、或线材问题 | 换线；确认笔记本在"扩展/复制"模式 |
| 出图但颜色不对 | 输入是 BGR/YUV 格式 | 调整 `hdmi_in.configure()` 的 `pixelformat` |
| 画面撕裂 | 输出时钟与输入未同步 | 本项目未做时钟同步（输入 74.25 MHz / 输出同频，一般够用） |
