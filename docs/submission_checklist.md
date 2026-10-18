# 提交清单（对照评分项）

本文件是交付前的最后一张表：**每个评分项对应哪些文件、证据在哪、现在什么状态**。
状态只有三种：`已验证`（有实测/运行证据）、`已实现未上板`、`未完成`。

生成日期：2026-10-18　工具链：Vivado / Vitis HLS 2026.1　板卡：PYNQ-Z2（XC7Z020，PYNQ 3.1.1 镜像）

## 一、按评分项

| 评分项（权重） | 交付物 | 证据 | 状态 |
| --- | --- | --- | --- |
| 创新性与应用价值（30） | 双通路架构（HDMI 流式 + AXI-DMA 批处理）共用同一算子；显式边界策略使硬件与软件可逐位比对 | `docs/architecture.md`、`report/design_report.md` §2 | 已验证（DMA 通路）/ 已实现未上板（HDMI 通路，缺显示设备） |
| 性能与资源优化（20） | PS vs PL 对比表：3108.4 ms → **15.8 ms**（196.7×），帧率 0.32 → 63.45 fps | `report/comparison.md`、`board/dma_sobel/metrics_board.csv`、原始日志 `metrics.csv` | 已验证 |
| 功能正确性与设计完整性（20） | 三个算子 C 仿真 0 误差；板上 DMA 回环与黄金参考**逐位一致**（0/2764800 通道） | `src/hls/*/README.md`、`board/dma_sobel/evidence/*.png`、`sim/sobel/test_sobel_dma_offline.py` | 已验证 |
| 大模型协作与技能包（15） | 21 条交互与纠错记录；4 个通用 Skill + 踩坑清单 | `report/ai_collaboration_log.md`、`skill/` | 已验证 |
| 文档质量与可复现性（15） | README 复现步骤、全脚本化构建、环境基线、PYNQ 移植记录 | `README.md`、`docs/env.md`、`docs/p3b_plan.md`、`build/**/build.bat` | 已验证 |

## 二、按交付物

| 交付物 | 位置 | 状态 |
| --- | --- | --- |
| HLS 算子：Sobel（流式 + 有界两个变体） | `src/hls/sobel/` | 已验证（板上逐位一致） |
| HLS 算子：Gaussian | `src/hls/gaussian/` | 已验证（C 仿真 0 误差、II=1、194.59 MHz） |
| HLS 算子：Sharpen | `src/hls/sharpen/` | 已验证（同上，含钳位路径覆盖） |
| 手写 RTL：AXI-Stream 三选一选择器 | `src/rtl/axis_mux3/` | 综合通过（36 LUT/0 FF）；功能仿真未跑通（本机 xsim 崩溃），未集成 |
| 手写 RTL：TLAST 生成器 | `src/rtl/axis_tlast_gen/` | 板上验证过其行为，最终版本未使用（有界核已足够） |
| DMA overlay 位流 | `board/dma_sobel/sobel_dma.bit|.hwh` | 已验证 |
| HDMI overlay 位流 | `board/hdmi_stream/sobel_hdmi.bit|.hwh` | 已实现未上板（缺 HDMI 线/显示器） |
| 软件黄金模型与比对 | `sim/common/`、`sim/*/golden_*.py`、`skill/golden_compare` | 已验证 |
| PS 软件基线 | `board/ps_baseline/ps_sobel.py` | 已验证（板上 3108 ms/帧） |
| 性能数据与对比表 | `sim/perf/make_comparison.py`、`report/comparison.md` | 已验证 |
| 通用 Skill ×4 + 踩坑清单 | `skill/` | 已验证 |
| 设计报告 | `report/design_report.md` | 已完成（含实测数据） |
| 大模型协作记录 | `report/ai_collaboration_log.md` | 已完成（21 条） |
| 英文 A4 海报 | — | **未完成**（决赛要求，需 AMD 模板） |

## 三、已知限制（报告里同样写明）

1. **HDMI 通路未在板上验证**：位流已构建、`.hwh` 离线校验通过，但缺显示器/采集卡，
   只能验证到"加载 + 输入锁定"这一步。DMA 通路已经提供了数字证据。
2. **算子切换 UI 未实现**：三个算子各自都有验证，但还没有把三路并行 + `axis_mux3`
   接进同一个 overlay（时序余量只有 +0.207 ns，需要先评估）。
3. **功耗未测**：PYNQ-Z2 无板载功率计，报告中没有功耗数据，也没有编造。
4. **`axis_mux3` 缺功能仿真**：本机 `xsim` 启动即崩（共享内存映射失败），
   只做到综合级验证；在交互式终端重跑 `build/rtl/axis_mux3/run_sim.tcl` 即可补上。

## 四、复现最短路径

```powershell
tools\env\vitis_hls.bat -f build\hls\sobel\run_hls.tcl          # 算子 + 仿真
tools\env\vitis_hls.bat -f build\hls\sobel_bounded\run_hls.tcl  # DMA 用的有界核
build\overlay_dma\build.bat                                     # 约 12 分钟出位流
# 板上（PYNQ 3.1.1，需 root + venv）：
sudo env XILINX_XRT=/usr PATH=/usr/local/share/pynq-venv/bin:/usr/bin:/bin HOME=/root \
  /usr/local/share/pynq-venv/bin/python3 sobel_dma.py
```
