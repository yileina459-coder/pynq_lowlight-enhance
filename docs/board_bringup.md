# PYNQ-Z2 上板连接指南

目标：让笔记本能打开板子的 Jupyter，并确认镜像版本。这是后面一切上板工作的前提，
不需要显示器、不需要 HDMI 线。

## 0. 你需要的东西

- PYNQ-Z2 板卡
- 已烧好 PYNQ 镜像的 microSD 卡（≥ 8 GB）
- micro USB 线（供电 + 串口，一根就够）
- 网线（接到家里的路由器/交换机）

## 1. 板卡设置（三步，别接错）

1. **Boot 跳线** 拨到 `SD` 位置 —— 从 SD 卡启动
2. **Power 跳线** 拨到 `USB` 位置 —— 用 micro USB 供电
   （若你有 12V 电源适配器，也可以拨到 `REG`，两种都行）
3. 把烧好镜像的 microSD 卡插进板子**背面**的卡槽

## 2. 接线

```text
  路由器/交换机 ──网线──> PYNQ-Z2 网口
  笔记本（同一路由器，网线或 WiFi 均可）

  笔记本 USB ──micro USB──> PYNQ-Z2 的 "PROG - UART" 口   （供电 + 串口控制台）
```

注意：PYNQ-Z2 上那个 micro USB 口同时承担供电和串口，所以**不要**用 USB 集线器，
直接插笔记本的 USB 口，避免供电不足。

## 3. 上电与观察

1. 把板子电源开关拨到 `ON`
2. **红色 LED 立刻亮** → 说明供电正常
3. 几秒后 **Done LED（黄/绿）亮** → 说明 FPGA 配置完成
4. 约 1 分钟后，**2 个蓝灯 + 4 个黄绿灯同时闪一下**，然后蓝灯开始闪、黄绿灯常亮
   → 系统启动完成，可以访问了

如果卡在某个灯不亮，见下面的排查表。

## 4. 打开 Jupyter

浏览器访问（同一局域网，DHCP 自动分配 IP）：

```text
http://pynq:9090
```

`pynq` 这个名字解析不了的话，用路由器管理页面查板子 IP，然后：

```text
http://<板子IP>:9090
```

默认用户名 / 密码：`xilinx` / `xilinx`。

## 5. 确认镜像版本（把结果发我）

在 Jupyter 新建一个 Notebook，运行：

```python
import pynq, sys
print("PYNQ:", pynq.__version__)
print("Python:", sys.version)
```

再开一个 Terminal（Jupyter 首页右上角 New → Terminal），运行：

```bash
ip a | grep "inet "
uname -a
```

把这两段输出发我，我需要知道：

- 镜像版本（决定我应该用哪个 Vivado 版本产出 `.bit/.hwh`，这是本项目最大的技术风险）
- 板子的 IP（后面写自动化脚本要用）

## 6. 排查表

| 现象 | 可能原因 | 处理 |
| --- | --- | --- |
| 红灯不亮 | USB 供电不足 / 跳线在 REG 但没接 12V | 换笔记本 USB 口，检查 Power 跳线 |
| 红灯亮、Done 不亮 | SD 卡没插好 / 镜像没烧成功 | 重插，或重烧镜像（用 balenaEtcher） |
| Done 亮但 `pynq:9090` 打不开 | 不在同一网段 / 路由器没给 DHCP | 查路由器客户端列表，改用 IP 访问 |
| 完全没有网络 | 网线坏 / 网口灯不亮 | 换网线；板子网口灯应亮 |
| 想直接看启动日志 | 串口控制台 | 用 PuTTY 连 COM 口，115200 8N1，用户名 `xilinx` 密码 `xilinx` |

## 7. 已知注意点

- 板子每次启动会重新从 SD 卡加载镜像，**你在 Jupyter 里存的 notebook 要放在
  `/home/xilinx/jupyter_notebooks`**，否则断电会丢。
- PYNQ 镜像默认没有 HDMI 输入/输出配置的额外依赖，base overlay 自带 `pynq.lib.video`。
- 如果没有显示器：`hdmi_out` 的输出无法直接看到，但**可以通过 DMA 把处理结果读回
  Python 存成 PNG** 来验证，这正是我们下一步要做的事，不需要买任何东西。
