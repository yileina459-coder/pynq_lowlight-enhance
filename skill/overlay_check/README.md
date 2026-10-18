# overlay_check — Overlay 加载前的离线校验

## 适用范围

任何要用 PYNQ 加载自定义 overlay 的项目，**换板卡、换 Vivado 版本同样适用**。
它不需要板卡，只要手里有 `.bit` 和 `.hwh`。

## 为什么需要它

自定义 overlay 上板失败时，板子在远端、报错往往只有一行、原因通常是结构性问题
（IP 没连、时钟没接、`.bit` 和 `.hwh` 不同名）。这些都能在上传前查出来。
这个工具把 `.hwh` 里的关键信息打印成人能读的清单，并给出明确的 PASS/FAIL。

## 使用方法

```bash
# 基本检查
python check_hwh.py board/dma_sobel/sobel_dma.hwh

# 额外要求某些 IP 必须存在（换项目时改这里）
python check_hwh.py --expect axi_dma_0,sobel_0 board/dma_sobel/sobel_dma.hwh
```

输出示例（本项目 DMA overlay 的真实输出）：

```text
file            : board/dma_sobel/sobel_dma.hwh
modules         : 6
  - axi_dma_0        axi_dma                 @ 0x41E00000-0x41E0FFFF
  - ps7              processing_system7      @ 0x00000000-0x1FFFFFFF
  - rst_100m         proc_sys_reset
  - sc_ctrl          smartconnect
  - sc_mem           smartconnect
  - sobel_0          sobel_stream
clocks          : 9
  - FCLK_CLK0: 100.000 MHz
  ...
HWH CHECK PASS
```

退出码 `0` = 通过，`1` = 有问题。

作为库使用：

```python
from check_hwh import check
ok, problems, info = check("design.hwh", expected=["axi_dma_0"])
```

## 检查项

| 检查 | 为什么 |
| --- | --- |
| `.bit` 与 `.hwh` 同名同目录 | PYNQ 按基名配对，不同名就报 "hwh not found" |
| 至少有一个 MODULE | 空 IP 列表意味着位流加载后什么都没暴露 |
| 存在 AXI DMA | 纯 PL 加速器通常要靠它搬数据；没有就说明设计缺了数据通路 |
| 至少一个时钟频率 | 没有时钟信息时 PYNQ 无法报告/设置时钟，也常意味着时钟没接 |
| `--expect` 指定的 IP 存在 | 防止"改了 tcl 但位流还是旧的"这类事故 |

## 失效条件

- 只解析 `.hwh` 的**结构**，不验证时序、不验证位流与器件是否匹配；
- 不代替上板：DMA 是否真能搬数据、中断是否挂上、地址是否正确，只有跑起来才知道；
- `.hwh` 的标签名在 Vivado 各版本间有差异（本项目遇到 2026.1 用大写 `INSTANCE`/
  `MODTYPE`、时钟频率放在 `PORT` 的 `CLKFREQUENCY` 属性上）。解析器对大小写都做了兼容，
  但**遇到更新的版本仍可能需要补**——这正是它要打印原始清单的原因：fail 时能一眼看出
  是"文件真的没有这个信息"还是"解析器不认识这个写法"。

## 已验证效果

- 对本项目 `board/dma_sobel/sobel_dma.hwh`（2026.1 生成）：
  识别出 6 个 IP、9 个时钟（全部 100 MHz）、DMA 寄存器窗口
  `0x41E00000-0x41E0FFFF`，判定 PASS；
- 反向验证：把同一个 `.hwh` 复制到没有配套 `.bit` 的目录后再查，正确报出
  `missing bitstream with the same base name` 并返回 1。
