# perf_collect — 测量数据入库与汇总

## 适用范围

任何需要"报告里的每个数字都能追溯到一次实际运行"的项目。不限于 FPGA：
只要你在测帧率、延迟、吞吐、资源、功耗，都可以用它记账。

## 为什么需要它

性能与资源优化的说服力来自**对比表**——只写“更快了”没法复核。
手抄进报告的数字有两个问题：一是容易抄错，二是无法复核。
这个工具把"测一次 → 记一行 → 自动出表"固定成流程，报告里的表直接由 `--summarize` 生成。

## 使用方法

```bash
# 记一条测量（CSV 不存在会自动建表头）
python perf_collect.py --csv metrics.csv --record \
    --design pl_dma --metric frame_rate --value 57.2 --unit fps \
    --conditions "1280x720, 100 MHz, per-row DMA" \
    --evidence board/log_20261018.txt

# 生成报告用的 markdown 表
python perf_collect.py --csv metrics.csv --summarize --out report/metrics.md

# 不带参数时等价于 --summarize
python perf_collect.py --csv metrics.csv
```

字段含义：

| 字段 | 说明 |
| --- | --- |
| `design` | 哪个实现，例如 `pl_sobel_stream` / `ps_numpy` / `ps_opencv` |
| `metric` | 测的是什么，例如 `frame_rate`、`latency_p99`、`lut_used` |
| `conditions` | 分辨率、时钟、传输尺寸、工具版本等前提条件 |
| `evidence` | 原始日志/截图的路径，复核时按这个找 |

作为库使用：

```python
from perf_collect import record, summarize
record("metrics.csv", "pl_dma", "frame_rate", 57.2, "fps",
       conditions="1280x720", evidence="board/log.txt")
print(summarize("metrics.csv"))
```

## 失效条件

- 它只做**记录与统计**，不判断数据是否可比。把不同分辨率、不同时钟下的数字混进
  同一行 `conditions` 里，汇总表就会算出一个没有意义的平均值——这是使用者的问题，
  工具不会拦你；
- 同一个 `design + metric` 下如果有多个 `conditions`，汇总表会把它们合并统计，
  条件之间用 `;` 连接显示。条件差异大时应该分开 design 命名；
- 数值列必须是数字，非数字行会被汇总时静默跳过（不会报错）。

## 已验证效果

```text
| design | metric | n | mean | min | max | unit | conditions |
| --- | --- | --- | --- | --- | --- | --- | --- |
| pl_dma | frame_rate | 2 | 57.65 | 57.2 | 58.1 | fps | 1280x720,100MHz |
```

（用两条人工记录验证的表头、聚合、去重条件逻辑；真实板卡数据在 DMA 版跑通后写入
`board/dma_sobel/metrics.csv`。）
