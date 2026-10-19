# -----------------------------------------------------------------------------
# Insert the enhance kernel into the PYNQ-Z2 base overlay block design.
#
# Same rewire as insert_sobel.tcl (cut the VDMA loopback, run the kernel on the
# live pixel stream), plus the two things the enhancement demo needs:
#
#   * a runtime configuration path, so the PS can change a preset while the video
#     keeps running. enhance_stream takes 59 config bits as plain ports; two
#     axi_gpio output channels (64 bits) plus enh_cfg_split drive them, which
#     avoids putting AXI-Lite into the kernel.
#
#   * a latency monitor. axis_latency_mon taps the kernel's input/output
#     handshakes and reports how many pixels are inside it; a second axi_gpio
#     channel pair lets the PS read that count and its peak. This turns
#     "latency is about one line" into a measured number.
#
# Args (tclargs): <base_dir> <enhance_ip_repo> <rtl_dir>
# -----------------------------------------------------------------------------
set base_dir    [lindex $argv end-2]
set enhance_ip  [lindex $argv end-1]
set rtl_dir     [lindex $argv end]

if {$base_dir eq "" || $enhance_ip eq "" || $rtl_dir eq ""} {
    puts "usage: insert_enhance.tcl <base_dir> <enhance_ip_repo> <rtl_dir>"
    exit 1
}
puts "base_dir  : $base_dir"
puts "enhance ip: $enhance_ip"
puts "rtl_dir   : $rtl_dir"

cd $base_dir
open_project {base/base.xpr}

# --- make both the HLS IP and the hand-written RTL visible --------------------
set repo_paths [get_property ip_repo_paths [current_project]]
if {[lsearch -exact $repo_paths $enhance_ip] < 0} {
    lappend repo_paths $enhance_ip
}
set_property ip_repo_paths $repo_paths [current_project]
update_ip_catalog

foreach rtl {enh_cfg_split.v axis_latency_mon.v} {
    set path [file join $rtl_dir $rtl]
    if {![file exists $path]} {
        puts "ERROR: missing RTL $path"
        exit 1
    }
    if {[llength [get_files -quiet $path]] == 0} {
        add_files -norecurse $path
    }
}
update_compile_order -fileset sources_1

open_bd_design {base/base.srcs/sources_1/bd/base/base.bd}

# --- cut the two ends of the VDMA loopback -----------------------------------
set in_port  [get_bd_intf_pins video/hdmi_in/out_stream]
set out_port [get_bd_intf_pins video/hdmi_out/in_stream]
if {[llength $in_port] == 0 || [llength $out_port] == 0} {
    puts "ERROR: video stream ports not found"
    exit 1
}
foreach pin [list $in_port $out_port] {
    foreach net [get_bd_intf_nets -of_objects $pin] {
        puts "deleting net [get_property NAME $net]"
        delete_bd_objs $net
    }
}

# --- the kernel ---------------------------------------------------------------
set enh [create_bd_cell -type ip -vlnv xilinx.com:hls:enhance_stream:1.0 enhance_0]
connect_bd_intf_net [get_bd_intf_pins video/hdmi_in/out_stream] [get_bd_intf_pins enhance_0/s_in]
connect_bd_intf_net [get_bd_intf_pins enhance_0/s_out]          [get_bd_intf_pins video/hdmi_out/in_stream]

# --- configuration: two 32-bit outputs -> 59 config bits ----------------------
set cfg_gpio [create_bd_cell -type ip -vlnv xilinx.com:ip:axi_gpio gpio_enh_cfg]
set_property -dict [list \
    CONFIG.C_GPIO_WIDTH {32} \
    CONFIG.C_GPIO2_WIDTH {32} \
    CONFIG.C_IS_DUAL {1} \
    CONFIG.C_ALL_OUTPUTS {1} \
    CONFIG.C_ALL_OUTPUTS_2 {1} \
] $cfg_gpio

set cfg_split [create_bd_cell -type module -reference enh_cfg_split enh_cfg_split_0]
connect_bd_net [get_bd_pins gpio_enh_cfg/gpio_io_o]  [get_bd_pins enh_cfg_split_0/cfg_lo]
connect_bd_net [get_bd_pins gpio_enh_cfg/gpio2_io_o] [get_bd_pins enh_cfg_split_0/cfg_hi]
foreach sig {clarity knee gain_lo gain_hi thresh binarize invert mono split_x} {
    connect_bd_net [get_bd_pins enh_cfg_split_0/$sig] [get_bd_pins enhance_0/$sig]
}

# --- latency monitor: taps only, never drives the stream ----------------------
set mon [create_bd_cell -type module -reference axis_latency_mon axis_latency_mon_0]
foreach {mon_pin enh_pin} [list \
        in_valid  enhance_0/s_in_TVALID \
        in_ready  enhance_0/s_in_TREADY \
        out_valid enhance_0/s_out_TVALID \
        out_ready enhance_0/s_out_TREADY] {
    connect_bd_net [get_bd_pins $enh_pin] [get_bd_pins axis_latency_mon_0/$mon_pin]
}

set lat_gpio [create_bd_cell -type ip -vlnv xilinx.com:ip:axi_gpio gpio_enh_lat]
set_property -dict [list \
    CONFIG.C_GPIO_WIDTH {32} \
    CONFIG.C_GPIO2_WIDTH {32} \
    CONFIG.C_IS_DUAL {1} \
    CONFIG.C_ALL_INPUTS {1} \
    CONFIG.C_ALL_INPUTS_2 {1} \
] $lat_gpio
connect_bd_net [get_bd_pins axis_latency_mon_0/count]     [get_bd_pins gpio_enh_lat/gpio_io_i]
connect_bd_net [get_bd_pins axis_latency_mon_0/max_count] [get_bd_pins gpio_enh_lat/gpio2_io_i]

# --- clocks and resets --------------------------------------------------------
# Kernel and monitor live in the video pixel-clock domain, which is what the
# rewire above connects them to. The two AXI GPIOs must sit on the PS AXI clock,
# so they copy whatever clock/reset an existing GPIO in the design already uses.
foreach {src dst} [list video/clk_142M enhance_0/ap_clk \
                        video/periph_resetn_clk142M enhance_0/ap_rst_n] {
    set nets [get_bd_nets -quiet -of_objects [get_bd_pins $src]]
    if {[llength $nets] == 0} {
        puts "ERROR: no net on $src"
        exit 1
    }
    connect_bd_net -net [get_property NAME [lindex $nets 0]] [get_bd_pins $dst]
}

set aclk_net  [get_property NAME [lindex [get_bd_nets -quiet -of_objects [get_bd_pins leds_gpio/s_axi_aclk]] 0]]
set arstn_net [get_property NAME [lindex [get_bd_nets -quiet -of_objects [get_bd_pins leds_gpio/s_axi_aresetn]] 0]]
puts "axi clock net: $aclk_net / reset net: $arstn_net"
foreach cell {gpio_enh_cfg gpio_enh_lat} {
    connect_bd_net -net $aclk_net  [get_bd_pins $cell/s_axi_aclk]
    connect_bd_net -net $arstn_net [get_bd_pins $cell/s_axi_aresetn]
}

# the monitor runs on the same pixel clock as the kernel
foreach pin {axis_latency_mon_0/aclk axis_latency_mon_0/aresetn} {
    set src [expr {$pin eq "axis_latency_mon_0/aclk" ? "video/clk_142M" : "video/periph_resetn_clk142M"}]
    connect_bd_net -net [get_property NAME [lindex [get_bd_nets -quiet -of_objects [get_bd_pins $src]] 0]] [get_bd_pins $pin]
}

# --- put the two GPIOs on the PS AXI-Lite fabric ------------------------------
# Find a crossbar with two free master ports; expanding one is the fallback.
set chosen ""
set base_idx -1
foreach cand {/ps7_0_axi_periph /ps7_0_axi_periph1 /ps7_0_axi_periph_1} {
    if {[llength [get_bd_cells -quiet $cand]] == 0} { continue }
    set n_mi [get_property CONFIG.NUM_MI $cand]
    set free {}
    for {set i 0} {$i < $n_mi} {incr i} {
        set p [get_bd_intf_pins -quiet [format "%s/M%02d_AXI" $cand $i]]
        if {[llength $p] > 0 && [llength [get_bd_intf_nets -quiet -of_objects $p]] == 0} {
            lappend free $i
        }
    }
    puts "$cand: NUM_MI=$n_mi free=$free"
    if {[llength $free] >= 2} {
        set chosen $cand
        set base_idx [lindex $free 0]
        break
    }
}
if {$chosen eq ""} {
    puts "no spare ports, growing /ps7_0_axi_periph by 2"
    set chosen /ps7_0_axi_periph
    set n_mi [get_property CONFIG.NUM_MI $chosen]
    set_property -dict [list CONFIG.NUM_MI [expr {$n_mi + 2}]] [get_bd_cells $chosen]
    set base_idx $n_mi
}

set idx $base_idx
foreach cell {gpio_enh_cfg gpio_enh_lat} {
    set port [format "%s/M%02d_AXI" $chosen $idx]
    puts "connect $cell to $port"
    connect_bd_intf_net [get_bd_intf_pins $port] [get_bd_intf_pins $cell/S_AXI]
    incr idx
}

assign_bd_address
validate_bd_design
save_bd_design

puts "RESULT: INSERT OK"
exit 0
