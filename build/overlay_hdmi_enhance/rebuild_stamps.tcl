# Rebuild the two stamp cells so they pick up the new `beats` port.
#
# update_module_reference does not refresh a block-design module reference against an
# edited RTL file: the cell kept its old port list (first_cycle, first_seen) and the
# new `beats` output was invisible, so the wiring step failed with
# "connect_bd_net requires at least two pins". Deleting and re-creating the cells
# makes Vivado re-infer the interface from the source.

set base_dir [lindex $argv end]
if {$base_dir eq ""} { puts "usage: rebuild_stamps.tcl <base_dir>"; exit 1 }

cd $base_dir
open_project {base/base.xpr}

set rtl {C:/Users/79171/Desktop/FPGA/src/rtl/axis_cycle_stamp/axis_cycle_stamp.v}
if {[llength [get_files -quiet $rtl]] == 0} { add_files -norecurse $rtl }
update_compile_order -fileset sources_1

open_bd_design {base/base.srcs/sources_1/bd/base/base.bd}

# Remember how the stream was wired before deleting.
set vpg     [get_bd_cells -quiet /vpg_0]
set kernel  [get_bd_cells -quiet /enhance_0]
set lat     [get_bd_cells -hierarchical -filter {NAME =~ "*gpio_enh_lat*"}]
if {[llength $vpg] == 0 || [llength $kernel] == 0 || [llength $lat] == 0} {
    puts "ERROR: expected vpg_0, enhance_0 and gpio_enh_lat in this design"
    exit 1
}
set lat [lindex $lat 0]

# The sink of stamp_out is the video hierarchy's input port.
set video_in [get_bd_intf_pins video/hdmi_out/in_stream]

foreach cell {/stamp_in_0 /stamp_out_0} {
    if {[llength [get_bd_cells -quiet $cell]] > 0} {
        puts "deleting $cell"
        delete_bd_objs [get_bd_cells $cell]
    }
}

set stamp_in  [create_bd_cell -type module -reference axis_cycle_stamp stamp_in_0]
set stamp_out [create_bd_cell -type module -reference axis_cycle_stamp stamp_out_0]

connect_bd_intf_net [get_bd_intf_pins vpg_0/m_axis]     [get_bd_intf_pins stamp_in_0/s_axis]
connect_bd_intf_net [get_bd_intf_pins stamp_in_0/m_axis]  [get_bd_intf_pins enhance_0/s_in]
connect_bd_intf_net [get_bd_intf_pins enhance_0/s_out]    [get_bd_intf_pins stamp_out_0/s_axis]
connect_bd_intf_net [get_bd_intf_pins stamp_out_0/m_axis] $video_in

# Same clock and reset as the kernel.
set aclk_net  [get_property NAME [lindex [get_bd_nets -quiet -of_objects [get_bd_pins enhance_0/ap_clk]] 0]]
set arstn_net [get_property NAME [lindex [get_bd_nets -quiet -of_objects [get_bd_pins enhance_0/ap_rst_n]] 0]]
foreach cell {stamp_in_0 stamp_out_0} {
    connect_bd_net -net $aclk_net  [get_bd_pins $cell/aclk]
    connect_bd_net -net $arstn_net [get_bd_pins $cell/aresetn]
}

# Beat counters to the latency GPIO.
foreach pin [list ${lat}/gpio_io_i ${lat}/gpio2_io_i] {
    foreach net [get_bd_nets -quiet -of_objects [get_bd_pins $pin]] {
        puts "disconnecting $pin"
        delete_bd_objs $net
    }
}
connect_bd_net [get_bd_pins stamp_in_0/beats]  [get_bd_pins ${lat}/gpio_io_i]
connect_bd_net [get_bd_pins stamp_out_0/beats] [get_bd_pins ${lat}/gpio2_io_i]

assign_bd_address
validate_bd_design
save_bd_design
puts "RESULT: STAMPS REBUILT"
exit 0
