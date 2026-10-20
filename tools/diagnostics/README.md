# 板上诊断脚本索引

这些是排查过程中写的**一次性取证脚本**，不是交付流程的一部分。留着的原因有两个：
出问题时能复现当时的判断，以及后来者不必重新发明这些探针。

跑法统一为（PYNQ 3.1.1 需要 root + venv）：

```bash
cd /home/xilinx/jupyter_notebooks/<目录>
sudo env XILINX_XRT=/usr PATH=/usr/local/share/pynq-venv/bin:/usr/bin:/bin HOME=/root \
  /usr/local/share/pynq-venv/bin/python3 <脚本>.py
```

## AXI-DMA 通路（`board/dma_sobel/`）

| 脚本 | 回答什么问题 |
| --- | --- |
| `diag_dma.py` | DMA 传输收不了尾时，先判断"有没有数据写进 DDR" |
| `diag_dma2.py` | 单行传输：写了多少字、S2MM 是否 idle |
| `diag_dma3.py` | 多种长度（8/16/32/64/256/1280 字）下的短差是否恒定 |
| `diag_dma4.py` | 逐字与黄金模型比对，确认"数据对、只是没有 TLAST" |
| `diag_dma5.py` | 用 2560 字传输证明 TLAST 生成器本身是否工作 |
| `probe_kernel.py` | 有界核的寄存器映射与 ap_start/ap_done 行为 |

结论见 `docs/dma_investigation.md`。

## 增强核 DMA 通路（`board/enhance_dma/`）

| 脚本 | 回答什么问题 |
| --- | --- |
| `panel_selftest.py` | 无浏览器环境下验证面板的 widget 树与首次运行 |
| `probe_latency.py` | 延迟 GPIO 的原始寄存器值（判断时间戳有没有在变） |

## HDMI 通路（`board/hdmi_stream_enhance/`、`board/hdmi_pattern/`）

| 脚本 | 回答什么问题 |
| --- | --- |
| `hdmi_stock_check.py` | 原厂 `base.bit` 是否能看到输入（把"我们的设计"和"板子"分开） |
| `hdmi_hpd_probe.py` | HPD 拉高后源端会不会重新枚举显示器 |
| `hdmi_out_start.py` | PYNQ 的 HDMI 输出必须额外调用 `start()` 这一点 |
| `hdmi_out_state.py` | `axi_dynclk`/`vtc_out` 的寄存器读数与驱动 `state()` |
| `hdmi_out_info.py` | 视频相关 IP 的地址与 `_display` 能力（只读，不写寄存器） |
| `hdmi_out_regs.py` | 早期版本，用错误的地址拼法读过 MMIO（会 SIGBUS），保留作为反例 |
| `stock_hdmi_out.py` | 用原厂 overlay 从 PS 推一帧到 HDMI OUT，验证输出端是否出信号 |

结论见 `docs/hdmi_source_study.md` 与 `docs/hdmi_status.md`。

## 两个通用坑（写在这里，免得再踩）

1. **不要用名字拼寄存器地址**：`hdmi_out_regs.py` 第一版拿 IP 名字去推 `phys_addr`，
   在 ARM 上直接 `Bus error`。地址一律从 `ol.ip_dict[name]['phys_addr']` 取。
2. **诊断脚本一律只读优先**：先读寄存器确认状态，再考虑写。写之前把原值打出来，
   这样即使后续失败，也知道改动前是什么。
