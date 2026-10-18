# 系统架构

目标数据通路：

```
HDMI 输入 -> VDMA / 视频采集 -> PL 算子流水线 -> VDMA / 视频输出 -> HDMI 输出
                                  |
                                  v
                    AXI-Lite 寄存器控制
                                  |
                                  v
                          PS Python / Jupyter
```

PL 侧负责实时图像算子处理，PS 侧负责参数配置、状态监控、UI 显示与性能统计。

## 官方基线

暂定使用 PYNQ 3.1.1 镜像，先不重建 bitstream，直接使用镜像自带的 `base.bit` 和 `base.hwh` 验证 HDMI 链路：

```python
from pynq.overlays.base import BaseOverlay

base = BaseOverlay("base.bit")
hdmi_in = base.video.hdmi_in
hdmi_out = base.video.hdmi_out

hdmi_in.configure()
hdmi_out.configure(hdmi_in.mode)
hdmi_in.start()
hdmi_out.start()
hdmi_in.tie(hdmi_out)
```

这一步只验证板卡、镜像、HDMI 输入输出和显示链路，不包含自定义算子。

## 视频处理路线选择

参考 PYNQ 官方 Video 文档，项目保留三种实现方式，分别承担不同作用：

| 路线 | 数据通路 | 用途 |
| --- | --- | --- |
| Python 软件处理 | PS 读帧 -> Python/OpenCV 处理 -> PS 写帧 | 软件基线、黄金参考、算法调试 |
| Pipeline 流式处理 | HDMI-In -> 自定义 AXI-Stream IP -> HDMI-Out | 实时低延迟主路线 |
| DMA 批处理 | HDMI-In -> VDMA -> DRAM -> 自定义 IP -> DRAM -> VDMA -> HDMI-Out | PS/PL 性能对比与吞吐测量 |

最终作品建议以 Pipeline 流式处理为实时展示路线，以 Python 软件版和 DMA 批处理版作为对比数据来源。

## 推荐数据通路

模式 A，官方回环：

```text
HDMI-In -> pixel_pack -> tie -> pixel_unpack -> HDMI-Out
```

模式 B，实时流式算子：

```text
HDMI-In -> pixel_pack -> [color_convert] -> 自定义 AXI-Stream 算子 -> [color_convert] -> pixel_unpack -> HDMI-Out
```

自定义算子插入位置优先选择 HDMI-In 的 `pixel_pack` 之后，或 HDMI-Out 的 `pixel_unpack` 之前；需要固定输入输出像素格式，并正确处理 AXI-Stream 的 `TLAST`、`TUSER`、`TKEEP`。

模式 C，DMA 对比：

```text
HDMI-In -> VDMA -> PS DRAM
PS DRAM -> DMA -> 自定义算子 -> DMA -> PS DRAM
PS DRAM -> VDMA -> HDMI-Out
```

## 从 XUP Sobel 开始的开发步骤

以 `Xilinx/xup_high_level_synthesis_design_flow` 的 `source/sobel` 为模板：

1. Part 1：在 Jupyter 中运行 OpenCV/Python 版 Sobel，得到软件结果和耗时。
2. Part 2：在 Vitis HLS 中完成 Sobel 核，运行 C 仿真、C 综合、C/RTL 协同仿真，导出 RTL IP；分别实现手写版和 Vitis Vision Library 版。
3. Part 3：在 Vivado 中导入 HLS 导出的 IP，连接 Zynq PS、DMA 和 Sobel 核，生成 bitstream。
4. 提取 `design_1_wrapper.bit` 和 `design_1.hwh`，重命名为同名文件后上传板卡。
5. 在 Jupyter 中加载 overlay，运行测试并记录结果。

关键脚本：

```bash
# HLS 仿真、综合、导出
cd <repo>/source/sobel/prj/<variant>/kernel
vitis_hls -f run_hls.tcl

# Vivado 集成与生成 bitstream
cd <repo>/source/sobel/prj/<variant>/overlay
vivado -mode batch -source run_vivado.tcl
```

上面的 `prj/<variant>` 是 XUP 教程 FIR 示例中的结构，Sobel 的具体子路径以克隆后 `source/sobel/` 实际目录为准。

## 各算子实现映射

| 算子 | 建议实现 |
| --- | --- |
| Sobel 边缘检测 | XUP 教程手写版或 `xf::cv::Sobel` |
| 高斯模糊 | `xf::cv::GaussianFilter` 或手写卷积核 |
| 锐化 | `xf::cv::Filter2D` 配锐化卷积核 |
| 色彩空间转换 | PYNQ `color_convert` 或 Vision 颜色转换函数 |

## 待确定项

- 工具链版本：暂定 PYNQ 3.1.1 + Vivado/Vitis 2026.1；但官方 PYNQ 3.1.1 overlay 使用 2024.1 构建，需用最小 overlay 验证 2026.1 产物的兼容性
- PYNQ-Z2 在 PYNQ 3.1.1 中仍提供官方 SD 卡镜像，版本支持已确认
- 主展示路线采用 Pipeline 流式处理还是 DMA 批处理，以及两者是否都要实现
- Overlay 中的视频 DMA 方案（VDMA 或自定义 DMA）
- 各算子的数据位宽、时钟频率与行缓冲结构
- PS 与 PL 的帧率统计和功耗测量方法
