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
#   * latency measurement. Two axis_cycle_stamp cells bracket the kernel on the
#     same clock and reset, so their counters agree and the difference between the
#     two first-beat stamps is the pipeline fill latency. A second axi_gpio reads
#     both stamps. On the DMA overlay this measured 16 pixel clocks = 160 ns.
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

foreach rtl {enh_cfg_split.v axis_cycle_stamp.v} {
    # each module lives in its own directory: src/rtl/<module>/<module>.v
    set path [file join $rtl_dir [file rootname $rtl] $rtl]
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

# --- fix the HDMI input PLL range -------------------------------------------
# dvi2rgb.vhd: "kClkRange : natural := 2;  -- MULT_F = kClkRange*5
#               (choose >=120MHz=1, >=60MHz=2, >=40MHz=3)"
# The stock design uses range 1 (>=120 MHz) yet advertises a 720p EDID, whose TMDS
# clock is 74.25 MHz: with MULT_F = 5 the VCO would be 371 MHz, below the MMCM
# minimum, so the input PLL cannot lock. Range 2 (60-120 MHz) is the right choice
# for 720p60 and is also why the unmodified PYNQ bitstream showed the same symptom.
foreach cell [get_bd_cells -quiet -filter {NAME =~ "*dvi2rgb*"}] {
    puts "setting kClkRange=2 on $cell (720p60 TMDS clock is 74.25 MHz)"
    set_property -dict [list CONFIG.kClkRange {2}] $cell
}


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

# --- latency: two stamps bracketing the kernel --------------------------------
# The stream was wired straight into the kernel above; rewrite it so the stamps
# sit on either side. Their counters start together, so t_out - t_in is the fill
# latency in pixel clocks.
# Collect the nets first and delete each once: iterating over pins would try to
# delete the same net twice and the second delete errors out.
set doomed {}
foreach pin [list video/hdmi_in/out_stream enhance_0/s_in enhance_0/s_out video/hdmi_out/in_stream] {
    if {[llength [get_bd_intf_pins -quiet $pin]] == 0} { continue }
    foreach net [get_bd_intf_nets -quiet -of_objects [get_bd_intf_pins $pin]] {
        if {[lsearch -exact $doomed $net] < 0} { lappend doomed $net }
    }
}
foreach net $doomed {
    puts "rewiring: delete net [get_property NAME $net]"
    delete_bd_objs $net
}
set stamp_in  [create_bd_cell -type module -reference axis_cycle_stamp stamp_in_0]
set stamp_out [create_bd_cell -type module -reference axis_cycle_stamp stamp_out_0]
connect_bd_intf_net [get_bd_intf_pins video/hdmi_in/out_stream] [get_bd_intf_pins stamp_in_0/s_axis]
connect_bd_intf_net [get_bd_intf_pins stamp_in_0/m_axis]         [get_bd_intf_pins enhance_0/s_in]
connect_bd_intf_net [get_bd_intf_pins enhance_0/s_out]           [get_bd_intf_pins stamp_out_0/s_axis]
connect_bd_intf_net [get_bd_intf_pins stamp_out_0/m_axis]        [get_bd_intf_pins video/hdmi_out/in_stream]

set lat_gpio [create_bd_cell -type ip -vlnv xilinx.com:ip:axi_gpio gpio_enh_lat]
set_property -dict [list \
    CONFIG.C_GPIO_WIDTH {32} \
    CONFIG.C_GPIO2_WIDTH {32} \
    CONFIG.C_IS_DUAL {1} \
    CONFIG.C_ALL_INPUTS {1} \
    CONFIG.C_ALL_INPUTS_2 {1} \
] $lat_gpio
connect_bd_net [get_bd_pins stamp_in_0/first_cycle]  [get_bd_pins gpio_enh_lat/gpio_io_i]
connect_bd_net [get_bd_pins stamp_out_0/first_cycle] [get_bd_pins gpio_enh_lat/gpio2_io_i]

# --- clocks and resets --------------------------------------------------------
# Kernel and monitor live in the video pixel-clock domain, which is what the
# rewire above connects them to. The two AXI GPIOs must sit on the PS AXI clock,
# so they copy whatever clock/reset an existing GPIO in the design already uses.
foreach {src dst} [list video/clk_142M enhance_0/ap_clk \
                        video/periph_resetn_clk142M enhance_0/ap_rst_n \
                        video/clk_142M stamp_in_0/aclk \
                        video/clk_142M stamp_out_0/aclk \
                        video/periph_resetn_clk142M stamp_in_0/aresetn \
                        video/periph_resetn_clk142M stamp_out_0/aresetn] {
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


# --- put the two GPIOs on the PS AXI-Lite fabric ------------------------------
# Find a crossbar with two free master ports; expanding one is the fallback.
# get_property wants an object, not a name - passing the name string fails with
# "Invalid option value '/ps7_0_axi_periph' specified for 'object'".
set chosen ""
set base_idx -1
foreach cand {/ps7_0_axi_periph /ps7_0_axi_periph1 /ps7_0_axi_periph_1} {
    set cell [get_bd_cells -quiet $cand]
    if {[llength $cell] == 0} { continue }
    set n_mi [get_property CONFIG.NUM_MI $cell]
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
    set cell [get_bd_cells $chosen]
    set n_mi [get_property CONFIG.NUM_MI $cell]
    set_property -dict [list CONFIG.NUM_MI [expr {$n_mi + 2}]] $cell
    set base_idx $n_mi
}

set idx $base_idx
foreach cell {gpio_enh_cfg gpio_enh_lat} {
    set port [format "%s/M%02d_AXI" $chosen $idx]
    puts "connect $cell to $port"
    connect_bd_intf_net [get_bd_intf_pins $port] [get_bd_intf_pins $cell/S_AXI]
    incr idx
}

# Ports created by growing the crossbar have no clock yet, and validate_bd_design
# refuses to pass:
#   ERROR: [BD 41-758] clock pins are not connected to a valid clock source:
#   /ps7_0_axi_periph/M08_ACLK  /ps7_0_axi_periph/M09_ACLK
# Copy the clock and reset nets from an existing master port of the same crossbar.
set m0_aclk  [get_property NAME [lindex [get_bd_nets -quiet -of_objects [get_bd_pins ${chosen}/M00_ACLK]] 0]]
set m0_arstn [get_property NAME [lindex [get_bd_nets -quiet -of_objects [get_bd_pins ${chosen}/M00_ARESETN]] 0]]
puts "new ports inherit aclk=$m0_aclk aresetn=$m0_arstn"
set idx $base_idx
foreach cell {gpio_enh_cfg gpio_enh_lat} {
    set suffix [format "M%02d" $idx]
    connect_bd_net -net $m0_aclk  [get_bd_pins ${chosen}/${suffix}_ACLK]
    if {$m0_arstn ne ""} {
        connect_bd_net -net $m0_arstn [get_bd_pins ${chosen}/${suffix}_ARESETN]
    }
    incr idx
}

assign_bd_address
validate_bd_design
save_bd_design

puts "RESULT: INSERT OK"
exit 0
