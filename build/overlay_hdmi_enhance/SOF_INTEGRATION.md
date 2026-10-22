# SOF（帧起始）集成流程

## 为什么需要它
_axi4s_vid_out 用 AXI4-Stream 的 TUSER 作为 SOF 把输入帧对齐到时序发生器（PG044）。本设计的
TUSER 来自 VDMA 且恒为 0，于是输出核自由跑，画面相位每次开机都不同（实测 0 / 45 / 89 px）。
src/hls/sof_gen/sof_gen.cpp 用 TLAST + 480 行计数器造出缺失的 SOF。

## 插入顺序（每一步都踩过坑）

1. **必须建在视频层级内**：
   `	cl
   current_bd_instance /video/hdmi_out
   create_bd_cell -type ip -vlnv xilinx.com:hls:sof_gen:1.0 sof_gen_0
   `
   在顶层创建再连过去，Vivado 会退化成**引脚级连接**，PYNQ 的 hwh 解析器会拒绝加载
   （MetadataObjectNotFound: s_axis_video_tdata[...]）。

2. **连接前把两端都清空**：create_bd_cell 可能留下半条网络（网络在，但新 cell 的引脚不在
   网络上），此时 connect_bd_intf_net 会报 lready connected 而不是给你接上。
   做法：先 delete_bd_objs 掉两端各自的网络，再连。
   uild/overlay_hdmi_enhance/insert_sof_v3.tcl 实现了这个逻辑。

3. **p_rst_n 必须显式连接**（ix_sof_reset2.tcl）：
   从 _axi4s_vid_out_0/aresetn 取网络在层级内解析不到，脚本会静默跳过。结果内核一直被复位，
   表现为 **VDMA 不再被消费**（演示里 RuntimeError: DMA channel not started），看起来像流路径
   坏了。改为连 /video/aresetn，并在保存后**回读验证**引脚确实有网络。

4. **复位跨时钟域要豁免**（cdc.xdc 末尾）：
   proc_sys_reset（100 MHz）驱动像素时钟域的复位，Vivado 按同步路径检查，
   加了 SOF 后布局变化就会失败（WNS −1.352）。这是构造上的异步路径。

## 结果
- 时序：WNS **+0.325 ns**，0 失败端点；
- 但**上板后流仍然停止**，说明还有别的原因（见 docs/hdmi_status.md 的后续记录）。
