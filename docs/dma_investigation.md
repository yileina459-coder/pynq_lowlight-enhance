# DMA 通路问题定位记录（2026-10-18，已在真实板卡上解决）

> **状态：已解决。** 根因是「流结束时流水线不排空」。修法是给 DMA 路线单独做一个
> 有界循环（`ap_ctrl_hs` + `n_pixels`）的核：`src/hls/sobel/sobel_bounded.cpp`，
> 并把它接上 AXI-Lite 控制（第一版漏接了，导致 `ap_start` 写不进去）。
> 修好后板上实测：**COMPARE PASS（bit-exact，0/2764800 通道不一致）**。
> 逐行传输 659 ms/帧；改成整帧一次传输后 **15.8 ms/帧（63.45 fps）**，
> 相对 PS numpy（3108 ms/帧）为 196.7×。修复细节见文末「解决」一节。

板卡：PYNQ-Z2，镜像 **PYNQ 3.1.1**（`/usr/local/share/pynq-venv`，内核 `6.6.10-xilinx-v2024.1`）。

## 好消息：三个前提都成立

| 事项 | 证据 |
| --- | --- |
| 2026.1 生成的 overlay 能被 3.1.1 加载 | `Overlay("sobel_dma.bit")` 成功，`DMA IP: <pynq.lib.dma.DMA object ...>` |
| 算子数据通路正确 | 与 numpy 黄金模型逐字比对 **0 个不一致**（`diag_dma4.py`，前 1264 个字） |
| DMA 本身能动 | `MM2S_DMASR = 0x00001002`（IDLE\|IOC，传输完成） |

## 坏消息：传输无法收尾

`diag_dma.py` / `diag_dma3.py` 的测量：

```text
 words   bytes  written  short by  s2mm_done
     8      32        0         8  False
    16      64        0        16  False
    32     128       16        16  False
    64     256       48        16  False
   256    1024      240        16  False
  1280    5120     1264        16  False
```

每次传输都**正好差 16 个字（一个 AXI burst）**，S2MM 永不完成 → 缺 TLAST。

## 加了 TLAST 生成器之后

`src/rtl/axis_tlast_gen`（自己写的 RTL，按拍计数生成 TLAST）插入 `sobel_0 → S2MM` 之间，
重建位流后重测：

```text
 1280 words -> written  1264, s2mm_done=False
 2560 words -> written  1280, s2mm_done=True     ← 生成器在第 1280 拍触发，提前结束传输
 3840 words -> written  1280, s2mm_done=True
```

这组数据同时证明了两件事：

1. **生成器工作正常**：2560 那一档传输在第 1280 拍被 TLAST 正常关闭；
2. **算子在流结束时没有把流水线排空**：给 1280 拍输入，出来的不足 1280 拍，
   所以生成器永远等不到它的第 1280 拍。

## 根因判断

HLS 核是 `ap_ctrl_none` + `while(1)` + `#pragma HLS PIPELINE II=1`：循环体先
`s_in.read()` 再 `s_out.write()`。输入一旦停止，流水线停在读端口，尾部若干拍
（与流水线深度同量级，估算 12 拍）没有排出来。对**连续视频流**（HDMI 路线）这没有影响——
表现为固定延迟；但对"一次传输一帧"的 DMA 路线，它导致每帧少一批数据且没有结束标志。

## 影响

- **HDMI 路线不受影响**（流永不停，延迟恒定）；
- **DMA 路线**目前不能作为"逐位比对"的验证手段，需要修；
- 已经能证明的是数据正确性（前 1264 个字逐字一致），这一点仍然有效。

## 修复选项（下一步）

1. **给 DMA 路线单独做一个"有界循环"的核**（`ap_ctrl_hs`，每次调用处理 N 个像素，
   自然排空）。代价：需要 start/done 握手，PYNQ 侧要按帧调用；好处是彻底解决。
2. 让 `axis_tlast_gen` 支持"软件写一个脉冲复位计数器"，使每个传输从 0 开始计数；
   但这仍然会丢掉尾部 12 拍，只是把"卡死"变成"每帧少 12 像素"——不可接受。
3. 在核里显式排空：读完最后一拍后再空转 L 拍输出剩余数据。HLS 里可以用
   "count 到 N 后继续走 L 次写"的写法，但会破坏 `ap_ctrl_none` 的连续性，且 HDMI 路线不需要。

结论：选 1，为 DMA 路线单独构建一个有界版本的核。

## 复现命令（板上）

```bash
cd /home/xilinx/jupyter_notebooks/sobel_dma
sudo env XILINX_XRT=/usr PATH=/usr/local/share/pynq-venv/bin:/usr/bin:/bin \
  /usr/local/share/pynq-venv/bin/python3 diag_dma3.py
```

注意：PYNQ 3.1.1 的 Jupyter 以 **root** 运行、且用 venv 里的 python；SSH 登录后必须
`sudo` + 指定 venv 解释器，否则 pyxrt 打不开设备 0（`No Devices Found`）。
