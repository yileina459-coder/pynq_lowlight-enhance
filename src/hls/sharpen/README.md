# sharpen — 流式 3×3 锐化核

## 是什么

中心加权的拉普拉斯锐化，逐通道 RGB：

```text
   0 -1  0
  -1  5 -1      out = 5*centre - (up + down + left + right)，饱和到 0..255
   0 -1  0
```

窗口结构与 Sobel / Gaussian 完全一致（三个轮转行缓冲 + 每行 3 抽头移位寄存器），
**II = 1，每时钟 1 像素**，边界策略也一致，因此三个算子共用同一套 Python 黄金参考。

## 为什么这里"饱和"而不是"回绕"

边缘一侧做差分会得到负值。硬件的 `ap_int<12>` 中间结果直接截断会得到 0xFF 之类的
翻转值（亮边变黑边），而软件参考用的是 `np.clip`。两边必须约定同一种处理：
**小于 0 取 0，大于 255 取 255**。测试台里专门统计了被钳位的像素数
（本测试图 1159 个低端钳位、822 个高端钳位），确保这个分支真的被覆盖到。

## 已验证结果（2026.1，`xc7z020clg400-1`，7 ns 约束）

| 项目 | 结果 |
| --- | --- |
| C 仿真 | `SHARPEN TB PASS`，9216 拍，第三帧逐像素 0 误差 |
| 钳位覆盖 | 低端 1159 像素、高端 822 像素（若为 0 会打 WARNING） |
| 吞吐 | II = 1，循环深度 9 |
| 时序 | 估计 Fmax **194.59 MHz** |
| 资源 | BRAM 9（3%）、LUT ≈ 1 k、FF ≈ 1 k、DSP 0 |

## 怎么跑

```bat
tools\env\vitis_hls.bat -f build\hls\sharpen\run_hls.tcl
python sim\sharpen\golden_sharpen.py --input data\images\test_720p.png ^
    --reference data\reference\sharpen_720p.png --border wrap
```

黄金参考脚本会顺带检查"锐化后方差必须变大"，若没有变大说明模型写错了。

## 四个算子的分工

| 算子 | 实现 |
| --- | --- |
| Sobel 边缘 | 本仓库 HLS（`src/hls/sobel`） |
| 高斯模糊 | 本仓库 HLS（`src/hls/gaussian`） |
| 锐化 | 本仓库 HLS（`src/hls/sharpen`） |
| 色彩空间转换 | **复用 PYNQ 官方 `color_convert` IP**（base overlay 里已有），不重写 |

最后一条是刻意的：色彩空间转换是查表/矩阵运算，官方 IP 已验证且就在视频通路里，
重写一遍只会增加出错面。自研集中在"卷积类算子"上，这也是本项目真正的设计工作量所在。
