# 视频进 / 视频出（校赛两天版）

> 一句话：**不碰 HDMI**。浏览器解码你选的视频，逐帧通过 AXI-DMA 送进 PL 的
> `enhance` 核，再把处理后的帧录成 `.webm` 下载。走的是项目里唯一已经逐位
> 验证过的通路，不需要重建位流，也不需要下采样/跨时钟域那套东西。

## 为什么是这条路，而不是 HDMI 直通

| 事实 | 出处 | 影响 |
| --- | --- | --- |
| DMA 通路 8 预设逐位一致（0/2764800 通道）、15.6 ms/帧 @720p | `board/enhance_dma/` | 两天内唯一可靠的"像素进、像素出" |
| HDMI OUT 只有 640×480 能驱动 | `docs/hdmi_status.md:114` | 直通要降分辨率 |
| HDMI IN 锁不上 640×480 | `docs/hdmi_status.md:129` | 直通还要再加缩放 + 跨时钟域 |
| 实时相机通路需要新 HLS 核 + CDC RTL + 重建 overlay（约 60 min/轮） | 上一轮讨论 | 两天里做不完，也不该在校赛上冒险 |

校赛要证明的是"真实视频经过 FPGA 核处理后可以看到变化，而且数字站得住"。
这条路正好只做这件事，把有风险的部分全留给决赛。

## 一、部署（板上，5 分钟）

文件（都放在同一个目录，例如 `/home/xilinx/jupyter_notebooks/enhance_dma/`）：

```
enhance_dma.bit          # 已有
enhance_dma.hwh          # 已有
enhance_dma.py           # 已有（DMA / 寄存器 / 打包工具函数）
enhance_video_server.py  # 新增，本次的服务器
sim/enhance/golden_enhance.py   # 已有就不用动（enhance_dma.py 会 import 它）
sim/common/image_ops.py         # 同上
```

> `panel.ipynb` 能在板上跑，就说明最后两个已经在位，不用再拷。

启动（与 `enhance_dma.py` 用同一条已验证的调用方式）：

```bash
cd /home/xilinx/jupyter_notebooks/enhance_dma
sudo env XILINX_XRT=/usr PATH=/usr/local/share/pynq-venv/bin:/usr/bin:/bin HOME=/root \
  /usr/local/share/pynq-venv/bin/python3 enhance_video_server.py \
  --size 640x480 --preset document
```

终端会打印：

```
engine      : dma(PL enhance kernel)
frames      : 640x480 (900 kB raw)
transport   : jpeg
open  http://192.168.x.x:8000/
```

## 二、操作（笔记本，Chrome 或 Edge）

1. 打开 `http://pynq:8000/`（或终端打印的 IP；端口占用时换 `--port 8080`）。
2. 先点 **自检**：不选视频，用内置测试图跑一帧。显示处理结果 = 板子、DMA、
   传输、浏览器四项全通。**这一步失败就不要往下走**，见第五节。
3. 选一个视频文件 → 选预设（`document` / `binarize` / `invert` 最能看出效果）
   → **开始处理**。
4. 处理过程中可以随时切预设，画面和录像都会跟着变。
5. 点 **停止并生成录像** → 出现下载链接，得到 `enhanced_<preset>_<时间>.webm`。
   录像画面是**左原始 / 右增强**，可以直接当演示素材。

页面上的数字都是真的：`板上 X ms/帧` 来自 `X-Frame-Ms` 响应头（PL 侧实测），
`往返 Y ms` 是浏览器测的整条路径，`Z fps` 是实际吞吐。

## 三、速度怎么调

瓶颈通常是 100 Mbit 网口，不是 PL。按需改 `--size` 和 `--transport`：

| 配置 | 每帧数据 | 估算帧率 | 用途 |
| --- | --- | --- | --- |
| `--size 640x480`（默认，jpeg） | ~110+140 kB | 15–25 fps | 校赛主力，字最清楚 |
| `--size 480x360`（jpeg） | ~70+90 kB | 25–35 fps | 更顺，投影时看不出差别 |
| `--size 320x240`（jpeg） | ~35+45 kB | 30–40 fps | 只求顺滑 |
| `--transport raw`（640×480） | 1.23 MB × 2 | 约 5 fps | **逐位一致**验证用，不要拿它演示 |

PL 自己的处理时间与尺寸成正比：720p 是 15.6 ms，640×480 约 5 ms，所以尺寸调小
对本机处理几乎没影响，省的全是网络。

## 四、传输模式（写进报告的那句话）

- `--transport jpeg`（默认）：画布 JPEG 编码后上网，两端各有一次有损压缩。
  **用于演示**，快，但不是逐位一致。
- `--transport raw`：每像素 4 字节（画布原生 RGBA）直接发，服务器去掉 alpha、
  处理后补回，字节不变。**用于验证**：在本机 mock 模式下对本机黄金模型是
  0/921600 差异（见 `.tmp/test_video_server.py` 的断言）。

报告里可以写：**演示链路用 JPEG 传输，验证链路用 raw 传输，raw 下与黄金模型
逐位一致，说明 FPGA 到浏览器的每一步都没有改动像素**。

## 五、故障排查

| 现象 | 最可能原因 | 处理 |
| --- | --- | --- |
| 页面打不开 | 网络 / 端口 | `ping pynq`；换 `--port 8080`；看板子终端有没有 traceback |
| 自检报 `板子报错：...` | overlay/DMA 没起来 | 先在板上跑 `python3 enhance_dma.py --presets document`，它才是硬件通路的基准 |
| 自检报 `请求失败` | 浏览器被代理 | 关掉系统代理，或用直连 IP |
| 选完视频一直不动 | 编码浏览器不支持 | 换 H.264 的 mp4；`Ctrl+Shift+J` 看控制台报错 |
| 帧率明显低于上表 | 走的是 100 Mbit 且尺寸大 | 降 `--size`；确认没有同时开 Jupyter 大文件传输 |
| 录像只有开头几帧 | MediaRecorder 限制 | 用 Chrome/Edge；一定要点"停止"让 `onstop` 落盘 |
| 画面偏色（红蓝反） | bit/hwh 与位流不是一对 | 三个文件必须同名同批；不要混用 `hdmi_*` 的 hwh |

## 六、校赛当天的清单

1. **提前录好一段 20–30 秒的成片**（左原始/右增强），存在 U 盘和笔记本各一份。
   现场无论如何都要有可播的东西。
2. 笔记本 + 板子：优先用**一根网线直连**（板子静态 IP `192.168.2.99`），
   不依赖场馆 Wi-Fi；带一个小路由器更稳。
3. 板子开机后只需重新加载 overlay（notebook 第一格或本脚本），不用重新烧卡。
4. 备用演示（不需要网络）：`panel.ipynb` 的 8 预设面板 + 已导出的
   `enhance_montage.png` 之类的静态对比图。
5. 讲的时候把三个数字报出来：8 预设 **0/2764800** 通道不一致、
   720p **15.6 ms/帧**、流水线延迟 **16 拍**。

## 七、口径（别说过头）

- 这条通路是 **AXI-DMA 批处理**：帧在 DDR 里，PS 搬运，PL 逐像素处理。
  可以说"PL 内的像素算法不经帧缓冲"，**不要**说整条链路"不经过帧缓冲"。
- "实时"在这是指"帧率足够看"，不是指 HDMI 那种一行延迟；一行延迟的证据
  在 `board/hdmi_pattern/`（内部图案源，16 个像素时钟），那是另一条通路。
- 决赛再上相机：`docs/hdmi_status.md` 里的输入侧结论和本轮讨论的
  下采样 + CDC 方案就是那一步的全部前置。

## 八、相关文件

| 文件 | 作用 |
| --- | --- |
| `board/enhance_dma/enhance_video_server.py` | HTTP 服务器 + 页面（本文件描述的东西） |
| `board/enhance_dma/enhance_dma.py` | 被复用的 DMA/寄存器/打包函数，也是硬件基准 |
| `board/enhance_dma/enhance_panel.py` | 不接视频时的交互面板（备用演示） |
| `sim/enhance/golden_enhance.py` | mock 模式下的软件替身，也是比对基准 |
