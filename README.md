# HDMI 实时视频处理流水线

参赛厂商：AMD

参赛平台：AMD 7 Series FPGA / Zynq-7000 SoC（实际使用 PYNQ-Z2，XC7Z020）

开发方向：AMD 自主选题（初级组）

作品名称：HDMI 实时视频处理流水线

作品简介：HLS 实现卷积类算子（Sobel 边缘、高斯模糊、锐化、色彩空间转换）并封装为 Overlay，Python/Jupyter 侧做参数控制与 UI；完整跑通 HDMI 输入 -> PL 流水线处理 -> HDMI 输出，并给出 PS 软件处理与 PL 硬件加速的帧率、延迟、资源、功耗对比数据。

## 当前状态

- [ ] 初始化仓库与目录结构
- [ ] 搭建 Vivado / Vitis 与 PYNQ-Z2 环境
- [ ] 跑通官方 base overlay 的 HDMI 回环
- [ ] 完成第一个 HLS 算子（Sobel）并上板验证
- [ ] 完成全部算子并封装为 Overlay
- [ ] 完成 Python/Jupyter 参数控制与 UI
- [ ] 完成 PS 与 PL 性能对比数据采集
- [ ] 沉淀通用 PYNQ Skill
- [ ] 完成大模型协作记录与设计报告

## 技术栈

- 硬件平台：PYNQ-Z2（Zynq-7000 XC7Z020）
- 开发工具：Vivado / Vitis 2026.1（推荐）或 2025.2
- PL 实现：Vitis HLS 或 Verilog/SystemVerilog RTL
- PS 实现：Python、Jupyter Notebook、PYNQ Overlay
- UI：ipywidgets

## 目录结构

```
.
├── README.md                 # 项目简介 + 复现步骤
├── docs/                     # 架构、接口、硬件搭建说明
├── src/                      # RTL / HLS / PS 侧源码
├── sim/                      # 仿真与验证脚本及结果
├── build/                    # 可复现构建脚本 + 综合实现报告
├── board/                    # 上板工程、运行脚本与实测输出
├── data/                     # 测试数据与参考结果
├── skill/                    # 可复用 Skill 与工作流
└── report/                   # 设计报告 + 大模型协作记录
```

## 核心开发路线

1. 环境准备：安装 Vivado/Vitis，PYNQ-Z2 烧录官方镜像，验证 HDMI 输入输出链路。
2. 算子设计：HLS/RTL 实现 Sobel、高斯模糊、锐化、色彩空间转换。
3. 封装 Overlay：完成寄存器映射、DMA 通路与 bitstream 生成。
4. PS 侧集成：Python/Jupyter 调用 Overlay，实现参数控制和 UI。
5. 基线对比：同一算法分别实现 PS 软件版和 PL 加速版，采集帧率、延迟、吞吐、资源、功耗。
6. 技能沉淀：把 Overlay 加载校验、DMA 封装、黄金参考比对、性能采集提炼为通用 Skill。
7. 报告与开源：完成设计报告、大模型协作记录，确保他人可从零复现。

## 评分对应证据

| 评分项 | 对应提交物 |
| --- | --- |
| 创新性与应用价值 30 | 完整 HDMI 视频处理系统 + 软硬件对比 |
| 性能与资源优化 20 | PS vs PL 帧率/延迟/吞吐/资源/功耗对比表 |
| 功能正确性与设计完整性 20 | 仿真结果、上板实测、算子正确性验证 |
| 大模型协作与技能包 15 | 大模型交互记录 + `skill/` 可复用内容 |
| 文档质量与可复现性 15 | README、Vivado tcl、设计报告、复现步骤 |

## 复现入口

环境搭建与复现步骤完成后在此处补充，保证其他队伍能够从零执行。

