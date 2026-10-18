# golden_compare — 逐位图像比对

## 适用范围

任何"硬件/加速器输出一张图，要跟软件参考图比对"的场景。不限于 FPGA、不限于 Sobel：
只要两边都能存成 PNG/JPG，就能用。

## 为什么不只用 PSNR

PSNR 30 dB 听起来不错，但可能意味着整张图偏了一个像素，或者亮度系数差了 1/256。
这类错误在图像流水线里非常常见，而且会让后面所有对比数据失真。
本工具默认 **tolerance = 0**，并且报出**第一个不一致像素的 (y, x, 通道, got, ref)**，
让失败直接指向 bug，而不是给一个笼统的分数。

## 使用方法

```bash
# 严格逐位比对
python golden_compare.py --got board_out.png --ref reference.png

# 跳过顶部 N 行（流水线预热 / 滤波器延迟）
python golden_compare.py --got out.png --ref ref.png --ignore-rows 2

# 允许 ±1 的舍入差，并输出放大后的差异图
python golden_compare.py --got out.png --ref ref.png --tolerance 1 --diff-out diff.png

# 机器可读报告，方便串进脚本
python golden_compare.py --got out.png --ref ref.png --json report.json
```

退出码：`0` = 在容差内一致；`1` = 不一致；`2` = 参数/文件错误。

作为库使用：

```python
from golden_compare import compare
report = compare("out.png", "ref.png", tolerance=0, ignore_rows=2)
assert report["ok"], report["first_diffs"]
```

## 失效条件

- 两边**不是同一内容**时没有意义（例如参考图是另一张测试图生成的）；
- 图像尺寸必须一致，工具不做缩放或裁剪对齐；
- 只比 RGB 三通道；带 alpha 的图会被 `convert("RGB")` 丢掉 alpha；
- 不做几何配准。如果硬件输出整体平移了一个像素，工具会报"大面积不一致"而不是"平移"，
  这时候应该先用 `--ignore-rows/--ignore-cols` 或肉眼定位平移量。

## 已验证效果

- 本仓库 `data/reference/sobel_720p.png` 与自己比对：0 个通道不一致，`COMPARE PASS`；
- 与输入图（内容不同）比对：2758573/2764800 个通道不一致，报出 `y=0 x=0 ch=R got=0 ref=255`，
  符合预期；
- `--tolerance 255` 时判定为 PASS，说明容差参数生效。
