# -----------------------------------------------------------------------------
# DMA verification overlay for the enhance kernel.
#
#   PS (Zynq)  -- M_AXI_GP0 -->  AXI-Lite  -->  AXI DMA (control)
#              -- S_AXI_HP0 <--  AXI       <--  DMA MM2S / S2MM
#   DMA MM2S --> enhance_bounded --> DMA S2MM
#
# Why a DMA overlay before the HDMI one
#   It proves the HLS kernel works in real silicon without needing a monitor:
#   the PS pushes a frame through the accelerator and reads the result back from
#   DDR, so the output can be compared bit-exactly against the golden model.
#   It also produces the first real latency / throughput numbers.
#
# Why the layout looks like this
#   * AXI DMA moves 32-bit words, so the kernel is built with ENH_PIX_W = 32.\n#   * enhance takes its 59 config bits on AXI-Lite, so the PS sets a preset per run.
#   * The kernel treats TLAST as end-of-line (that is what PYNQ's pixel_pack
#     produces on the HDMI path), therefore the test software must issue one
#     transfer per row rather than one per frame. See board/README.md.
#   * FCLK_CLK0 is 100 MHz, the same clock the PYNQ image already configures at
#     boot, so the overlay does not depend on PYNQ reconfiguring the PS.
# -----------------------------------------------------------------------------
set script_dir [file dirname [file normalize [info script]]]
set repo_root  [file normalize [file join $script_dir ".." ".."]]
set part_name  "xc7z020clg400-1"
set proj_dir   [file join $script_dir "proj"]
set out_dir    [file join $script_dir "out"]
set iprepo_dir [file join $script_dir "iprepo"]

file mkdir $out_dir
if {![file exists $iprepo_dir]} {
    error "IP repository not found at $iprepo_dir - run build.bat, it unpacks the HLS export first"
}

puts "=== CREATE PROJECT ==="
create_project -force enhance_dma $proj_dir -part $part_name
set_property ip_repo_paths [list $iprepo_dir] [current_project]
update_ip_catalog -rebuild

# Hand-written RTL: the latency monitor (taps only, never drives the stream).
foreach rtl {axis_cycle_stamp.v} {
    set path [file join $repo_root "src" "rtl" "axis_cycle_stamp" $rtl]
    if {![file exists $path]} { error "missing RTL: $path" }
    add_files -norecurse $path
}
update_compile_order -fileset sources_1

# No hand-written RTL otherwise: the kernel's own TLAST is enough
# once it is the bounded variant. axis_tlast_gen stays in src/rtl as a documented
# experiment (see docs/dma_investigation.md) but is not instantiated here.

puts "=== BLOCK DESIGN ==="
create_bd_design "design_1"
current_bd_design "design_1"

# --- Zynq PS ---------------------------------------------------------------
set ps7 [create_bd_cell -type ip -vlnv xilinx.com:ip:processing_system7 ps7]
set_property -dict [list \
    CONFIG.PCW_USE_M_AXI_GP0 {1} \
    CONFIG.PCW_USE_S_AXI_HP0 {1} \
    CONFIG.PCW_USE_FABRIC_INTERRUPT {0} \
    CONFIG.PCW_EN_CLK0_PORT {1} \
    CONFIG.PCW_FPGA0_PERIPHERAL_FREQMHZ {100} \
] $ps7

# --- AXI DMA, simple mode, 32-bit streams ----------------------------------
set dma [create_bd_cell -type ip -vlnv xilinx.com:ip:axi_dma axi_dma_0]
set_property -dict [list \
    CONFIG.c_include_sg {0} \
    CONFIG.c_sg_include_stscntrl_strm {0} \
    CONFIG.c_m_axi_mm2s_data_width {32} \
    CONFIG.c_m_axis_mm2s_tdata_width {32} \
    CONFIG.c_m_axi_s2mm_data_width {32} \
    CONFIG.c_s_axis_s2mm_tdata_width {32} \
    CONFIG.c_sg_length_width {23} \
] $dma

# c_sg_length_width also sizes the simple-mode buffer length register. The
# default is 14 bits, i.e. a maximum transfer of 16383 bytes - far too small for
# a 3.6 MB frame, and the failure only shows up at runtime as
#   ValueError: Transfer size ... exceeds the maximum DMA buffer size 16383
# 23 bits allows 8 MB, enough for 1080p as well.

# --- the kernel ------------------------------------------------------------
set enh [create_bd_cell -type ip -vlnv xilinx.com:hls:enhance_bounded:1.0 enhance_0]

# --- latency measurement ----------------------------------------------------
# Two cycle-stamp cells, one before and one after the kernel, share a clock and a
# reset, so their counters are identical and the two stamps differ by exactly the
# pipeline fill latency. A single cell cannot do this: in a pass-through its own
# input and output fire in the same cycle (this was built and measured as 0).
set stamp_in  [create_bd_cell -type module -reference axis_cycle_stamp stamp_in_0]
set stamp_out [create_bd_cell -type module -reference axis_cycle_stamp stamp_out_0]
connect_bd_intf_net [get_bd_intf_pins axi_dma_0/M_AXIS_MM2S]  [get_bd_intf_pins stamp_in_0/s_axis]
connect_bd_intf_net [get_bd_intf_pins stamp_in_0/m_axis]      [get_bd_intf_pins enhance_0/s_in]
connect_bd_intf_net [get_bd_intf_pins enhance_0/s_out]        [get_bd_intf_pins stamp_out_0/s_axis]
connect_bd_intf_net [get_bd_intf_pins stamp_out_0/m_axis]     [get_bd_intf_pins axi_dma_0/S_AXIS_S2MM]

set lat_gpio [create_bd_cell -type ip -vlnv xilinx.com:ip:axi_gpio gpio_lat]
set_property -dict [list \
    CONFIG.C_GPIO_WIDTH {32} \
    CONFIG.C_GPIO2_WIDTH {32} \
    CONFIG.C_IS_DUAL {1} \
    CONFIG.C_ALL_INPUTS {1} \
    CONFIG.C_ALL_INPUTS_2 {1} \
] $lat_gpio
connect_bd_net [get_bd_pins stamp_in_0/first_cycle]  [get_bd_pins gpio_lat/gpio_io_i]
connect_bd_net [get_bd_pins stamp_out_0/first_cycle] [get_bd_pins gpio_lat/gpio2_io_i]


# The TLAST generator that was trialled here is gone: once the bounded kernel
# emits every beat, its own passthrough TLAST arrives exactly where the DMA needs
# it. A beat-counted generator would instead fire in the middle of a whole-frame
# transfer and close it early. The RTL stays in src/rtl/axis_tlast_gen for the
# record, and its diagnosis is written up in docs/dma_investigation.md.

# --- interconnect ----------------------------------------------------------
# Control path: one PS master, two slaves (DMA registers + kernel control).
# The kernel has an AXI-Lite control interface because it is the bounded variant
# (ap_start / ap_done / n_pixels). Leaving it unconnected silently produces a
# design where the kernel can never be started - which is exactly what happened
# the first time this overlay was rebuilt, so the second slave is not optional.
set sc_ctrl [create_bd_cell -type ip -vlnv xilinx.com:ip:smartconnect sc_ctrl]
set_property -dict [list CONFIG.NUM_SI {1} CONFIG.NUM_MI {3}] $sc_ctrl

# Memory path: two masters (MM2S, S2MM), one slave (HP0).
set sc_mem [create_bd_cell -type ip -vlnv xilinx.com:ip:smartconnect sc_mem]
set_property -dict [list CONFIG.NUM_SI {2} CONFIG.NUM_MI {1}] $sc_mem

# --- reset -----------------------------------------------------------------
set rst [create_bd_cell -type ip -vlnv xilinx.com:ip:proc_sys_reset rst_100m]
connect_bd_net [get_bd_pins ps7/FCLK_CLK0]          [get_bd_pins rst_100m/slowest_sync_clk]
connect_bd_net [get_bd_pins ps7/FCLK_RESET0_N]      [get_bd_pins rst_100m/ext_reset_in]

# --- clocks and resets -----------------------------------------------------
# The PS AXI ports need their own aclk inputs, otherwise validate_bd_design
# fails with "clock pins are not connected to a valid clock source".
foreach pin {
    ps7/M_AXI_GP0_ACLK
    ps7/S_AXI_HP0_ACLK
    axi_dma_0/s_axi_lite_aclk
    gpio_lat/s_axi_aclk
    axi_dma_0/m_axi_mm2s_aclk
    axi_dma_0/m_axi_s2mm_aclk
    enhance_0/ap_clk
    stamp_in_0/aclk
    stamp_out_0/aclk
    sc_ctrl/aclk
    sc_mem/aclk
} {
    connect_bd_net [get_bd_pins ps7/FCLK_CLK0] [get_bd_pins $pin]
}
foreach pin {
    axi_dma_0/axi_resetn
    gpio_lat/s_axi_aresetn
    enhance_0/ap_rst_n
    stamp_in_0/aresetn
    stamp_out_0/aresetn
    sc_ctrl/aresetn
    sc_mem/aresetn
} {
    connect_bd_net [get_bd_pins rst_100m/peripheral_aresetn] [get_bd_pins $pin]
}

# --- AXI interconnects -----------------------------------------------------
connect_bd_intf_net [get_bd_intf_pins ps7/M_AXI_GP0]      [get_bd_intf_pins sc_ctrl/S00_AXI]
connect_bd_intf_net [get_bd_intf_pins sc_ctrl/M00_AXI]    [get_bd_intf_pins axi_dma_0/S_AXI_LITE]
connect_bd_intf_net [get_bd_intf_pins sc_ctrl/M01_AXI]    [get_bd_intf_pins enhance_0/s_axi_ctrl]
connect_bd_intf_net [get_bd_intf_pins sc_ctrl/M02_AXI]    [get_bd_intf_pins gpio_lat/S_AXI]
connect_bd_intf_net [get_bd_intf_pins axi_dma_0/M_AXI_MM2S] [get_bd_intf_pins sc_mem/S00_AXI]
connect_bd_intf_net [get_bd_intf_pins axi_dma_0/M_AXI_S2MM] [get_bd_intf_pins sc_mem/S01_AXI]
connect_bd_intf_net [get_bd_intf_pins sc_mem/M00_AXI]     [get_bd_intf_pins ps7/S_AXI_HP0]

# --- the actual data path --------------------------------------------------
# MM2S -> kernel -> latency monitor -> S2MM (the monitor is a pass-through)
# (the stream path itself is wired above: MM2S -> stamp_in -> kernel -> stamp_out -> S2MM)

# --- address map -----------------------------------------------------------
# Offset left to the auto-assign algorithm on purpose: PYNQ reads the real
# address out of the .hwh, so hard-coding 0x40400000 only adds a conflict risk
# (and `offset` is read-only on the segment in 2026.1).
assign_bd_address

validate_bd_design
save_bd_design

puts "=== WRAPPER ==="
set bd_file [get_files design_1.bd]
set wrapper [make_wrapper -files $bd_file -top]
add_files -norecurse $wrapper
set_property top design_1_wrapper [current_fileset]
update_compile_order -fileset sources_1

puts "=== IMPLEMENTATION (this takes 10-20 min) ==="
launch_runs impl_1 -to_step write_bitstream -jobs 8
wait_on_run impl_1

set status [get_property STATUS [get_runs impl_1]]
puts "impl_1 status: $status"
if {[string first "write_bitstream Complete" $status] < 0} {
    error "implementation failed: $status"
}

puts "=== REPORTS ==="
open_run impl_1
report_utilization      -file [file join $out_dir util_impl.rpt]
report_timing_summary   -file [file join $out_dir timing_impl.rpt]
report_clock_utilization -file [file join $out_dir clocks_impl.rpt]
close_design

puts "=== EXPORT HANDOFF ==="
# PYNQ loads a .bit and looks for a .hwh with the same base name, so the XSA is
# produced here and unpacked into those two files by build.bat.
set xsa [file join $out_dir design_1.xsa]
write_hw_platform -fixed -force -include_bit $xsa
puts "wrote $xsa"

puts "RESULT: OK"
exit 0
