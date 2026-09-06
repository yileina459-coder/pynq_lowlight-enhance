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

## 待确定项

- Overlay 中的视频 DMA 方案（VDMA 或自定义 DMA）
- 各算子的数据位宽、时钟频率与行缓冲结构
- PS 与 PL 的帧率统计和功耗测量方法

