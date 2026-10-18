# 参考资源调研

本文件记录项目可复用的官方资料，重点是“先跑通官方基线，再做自定义算子”的开发路径。

## 结论

直接作为项目基线的三类资源：

- **AMD XUP HLS 设计流程教程**：已经覆盖 PYNQ-Z2 上的 Sobel、HLS 核、Vivado overlay、Jupyter 上板验证。
- **PYNQ 官方文档**：覆盖 base overlay、HDMI 输入输出、视频处理三种集成方式。
- **Vitis Libraries Vision**：提供 Sobel、高斯、卷积、色彩转换等预优化算子。

AMD 的 UG 系列手册作为工具参考书，按需查阅即可，不必通读。

## 资源清单

| 资源 | 链接 | 在本项目中的用途 | 优先度 |
| --- | --- | --- | --- |
| XUP High-Level Synthesis Design Flow | <https://xilinx.github.io/xup_high_level_synthesis_design_flow/> | 完整参考实现：软件基线、HLS 核、overlay、上板测试 | 极高 |
| XUP Sobel 专题 | <https://xilinx.github.io/xup_high_level_synthesis_design_flow/sobel.html> | 手写 Sobel 与 Vitis Vision Sobel 的对比流程 | 极高 |
| XUP 仓库 | <https://github.com/Xilinx/xup_high_level_synthesis_design_flow> | 源码、Tcl、Jupyter Notebook | 极高 |
| PYNQ 官方文档 | <https://pynq.readthedocs.io/en/latest/index.html> | PS 侧、overlay、驱动与开发方式 | 极高 |
| PYNQ Video 章节 | <https://pynq.readthedocs.io/en/latest/pynq_libraries/video.html> | HDMI 输入输出、视频管线、三种处理方式 | 极高 |
| Vitis Libraries | <https://github.com/Xilinx/Vitis_Libraries> | Vision L1 预优化图像算子 | 高 |
| UG1399 Vitis HLS 用户指南 | <https://docs.amd.com/r/en-US/ug1399-vitis-hls> | HLS pragma、接口、仿真、综合、导出 RTL IP | 高 |
| UG901 Vivado 综合用户指南 | <https://docs.amd.com/r/en-US/ug901-vivado-synthesis> | 综合属性、RTL 编码风格、综合问题排查 | 中 |
| UG904 Vivado 实现用户指南 | <https://docs.amd.com/r/en-US/ug904-vivado-implementation> | 布局布线、时序收敛、实现报告 | 中 |
| UG949 UltraFast 设计方法学指南 | <https://docs.amd.com/r/en-US/ug949-vivado-design-methodology> | 设计预算、资源/功耗/时序优化 | 中 |

## 核心参考：XUP HLS Sobel

XUP 教程定位为 Vitis HLS 2023.2 + Vivado 2023.2，支持 PYNQ-Z2 和 KV260。教程把实验拆成三部分：

| 阶段 | 内容 | 环境 |
| --- | --- | --- |
| Part 1 | 用 Python/OpenCV 完成软件实现，作为黄金参考和性能基线 | Jupyter Notebook |
| Part 2 | 编写并优化 HLS 核，支持手写版和 Vitis Vision Library 版 | Vitis HLS |
| Part 3 | 在 Vivado 中集成 IP，生成 overlay，回到 Jupyter 上板测试 | Vivado + PYNQ |

仓库中与本项目最相关的 Sobel 资料位于 `source/sobel/`，建议进入仓库后直接以该目录为模板：

```text
source/sobel/
├── readme.md                              # Sobel 项目总览
├── notebook/
│   └── sobel_all.ipynb                    # 软件实现 + 上板验证
├── kernel/
│   ├── sobel.hpp                          # HLS 核头文件
│   ├── sobel_opt.cpp                      # HLS 核主体
│   └── sobel_tb.cpp                       # C 仿真 testbench
└── tutorial/
    ├── hand_coded_gui_flow.md             # 手写 Sobel 的 GUI 流程
    ├── vision_library_win.md              # Windows 安装 Vitis Vision Library
    └── vision_library_linux.md            # Linux 安装 Vitis Vision Library
```

命令行流程可参考仓库内的 `docs/pbl.md`，与 FIR 示例一致：

```bash
git clone https://github.com/Xilinx/xup_high_level_synthesis_design_flow.git
export LAB_WORK_DIR="<repo>/source"
source <Vitis_install_path>/Vitis/2023.2/settings64.sh

# Part 2：HLS 仿真、综合、导出 IP
cd "$LAB_WORK_DIR/<project>/prj/<variant>/kernel"
vitis_hls -f run_hls.tcl

# Part 3：Vivado 集成并生成 bitstream
cd "$LAB_WORK_DIR/<project>/prj/<variant>/overlay"
vivado -mode batch -source run_vivado.tcl
```

最终从 Vivado 结果中提取 `.bit` 和 `.hwh`，两者文件名必须一致，例如：

```text
design_1_wrapper.bit -> sobel.bit
design_1.hwh         -> sobel.hwh
```

然后放到板子同一目录下，通过 `Overlay("sobel.bit")` 加载。

注意：GUI 教程中部分截图以 KV260 为例，换到 PYNQ-Z2 时应选择 PYNQ-Z2 开发板文件，器件为 `xc7z020clg400-1`。

## 核心参考：PYNQ Video

PYNQ 官方 Video 文档给出了 HDMI 子系统的基本结构和三种处理方式：

1. **Python 处理**：`hdmi_in.readframe()` 取帧，处理后 `hdmi_out.writeframe()` 写回。适合做软件基线、黄金参考和调试，但速度慢。
2. **Pipeline 处理**：把自定义 AXI-Stream IP 插入 HDMI 输入或输出侧的像素流中。适合实时低延迟处理，是最终作品的主要路线。
3. **Batch 处理**：通过 DMA/VDMA 在 PS DRAM 与自定义 IP 之间搬运整帧。适合做 PS 与 PL 的性能对比，但 DRAM 带宽可能成为瓶颈。

官方 HDMI 回环示例：

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

自定义流式算子建议插入在 HDMI-In 的 `pixel_pack` 之后，或 HDMI-Out 的 `pixel_unpack` 之前；颜色空间转换块 `color_convert` 可在自定义 IP 前后配合使用。

## 核心参考：Vitis Libraries Vision

Vitis Libraries 中的 Vision L1 提供可直接调用的图像处理核，与 XUP Sobel 教程形成互补：

- Sobel：`xf::cv::Sobel`
- 高斯模糊：`xf::cv::GaussianFilter`
- 锐化/通用卷积：`xf::cv::Filter2D`
- 色彩空间转换：Vision 库中对应的颜色转换函数，或 PYNQ video 子系统的 `color_convert`

这些核已经针对 AMD FPGA 做过优化，优先考虑复用；需要更细粒度控制时再回到手写 HLS。

## 版本与使用注意

- **本项目暂定版本**：PYNQ 镜像 `3.1.1`，Vivado/Vitis `2026.1`。
- PYNQ 3.1.1 官方 SD 卡镜像中的 overlay 使用 **Vivado 2024.1 / Petalinux 2024.1** 构建。官方 `base.bit` 可直接用于 HDMI 回环验证，不需要重建。
- 使用 Vivado 2026.1 生成自定义 overlay 时，和 PYNQ 3.1.1 官方镜像的构建工具链存在版本差。虽然算法和 IP 集成流程可以复用，但需要先做一个最小 overlay 冒烟测试，确认 `.bit/.hwh` 能被 PYNQ 3.1.1 正确解析和加载。
- XUP 教程当前配套 Vitis/Vivado **2023.2**。本项目使用 2026.1，算法、目录和流程可复用，但 Tcl、board files、Vitis Libraries 版本需要适配。
- 板子镜像、`.bit`、`.hwh`、PYNQ Python 驱动必须来自同一套版本，避免 HWH 解析或驱动不匹配。
- PYNQ-Z2 的 HDMI 前端口官方资料说明最高支持 1080p，但受差分引脚速率限制，官方支持到 720p。项目在确定分辨率和帧率目标时建议先以 720p 为验证基线。
- Windows 下避免过深路径，Vivado 对路径长度敏感；建议仓库路径保持较短。
