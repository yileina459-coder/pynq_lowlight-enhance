# dma_stream — AXI-DMA 搬运与缓存一致性封装

## 适用范围

任何"PS 通过 AXI DMA 把数据送进 PL、再读回来"的 PYNQ 项目，**换板卡、换算子同样适用**。
不绑定 Sobel，也不绑定图像——只要数据是一段连续的 DDR 缓冲区。

## 它解决的三个具体问题

1. **找 DMA 实例**：`overlay.axi_dma_0` 在不同 PYNQ 版本里有时是 `pynq.lib.dma.DMA`，
   有时只是 `DefaultIP`（没有 `sendchannel`）。`find_dma()` 两种都处理。
2. **缓存一致性**：发数据前必须 `flush()`，收数据后必须 `invalidate()`。
   漏掉前者会送进旧数据，漏掉后者会读到旧数据，两者都表现得像"逻辑写错了"。
3. **卡死没有信息**：`channel.wait()` 不返回时，Notebook 只是"没反应"。这里用带超时的
   等待，超时会明确说是 MM2S 还是 S2MM 没完成。

## 使用方法

```python
from pynq import Overlay, allocate
from dma_stream import find_dma, transfer_rows, transfer_block

ol = Overlay("design.bit")
dma = find_dma(ol)

src = allocate(shape=(1280 * 720,), dtype=np.uint32)
dst = allocate(shape=(1280 * 720,), dtype=np.uint32)
src[:] = frame_words

# 内核把 TLAST 当作行尾 → 一行一次传输
seconds = transfer_rows(dma, src, dst, width=1280, height=720)

# 内核只关心缓冲区结束 → 整帧一次传输，快得多
seconds = transfer_block(dma, src, dst, nbytes=1280 * 720 * 4)
```

返回的是**这段传输的墙钟时间**，可以直接作为性能数据记进 `skill/perf_collect`。

## 失效条件

- 只支持**简单模式**（simple mode）的 AXI DMA；Scatter-Gather 需要另一套寄存器操作；
- `transfer_rows` 的正确性依赖"内核按 TLAST 断行"。若内核其实按固定宽度计数，
  逐行传输会正常工作但白付一遍开销；若内核按整帧处理，用 `transfer_rows` 反而会打乱它；
- 不处理中断，靠轮询 `idle` 位。DMA 频率很高时轮询会占用 CPU（本项目可接受）；
- 不做缓冲区分配，`allocate()` 仍需调用者负责；不检查物理地址对齐；
- 超时只是**放弃等待**，不会中止 DMA，硬件可能仍在传输。超时后应重新加载 overlay 或复位 DMA。

## 已验证效果

- `sim/sobel/test_sobel_dma_offline.py` 用 numpy 假 DMA 复现内存行为，
  驱动真实的 `board/dma_sobel/sobel_dma.py`（其内部使用同样的传输逻辑），
  端到端结果为 `COMPARE PASS (bit-exact)`；
- 同一路径在 `transfer_rows` 中按行传递 720 次，与黄金参考逐位一致——
  说明偏移计算（`row * width * pixel_bytes`）与缓存维护次序正确。

板上真实硬件的逐次传输时间待 DMA 回环实测后补入本节。
