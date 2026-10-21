# Replace the reset gate with the clocked bridge (new module name).
#
# Vivado caches block-design module references by module name, so re-creating a cell for
# an edited module keeps the old port list ("the gate has no aclk pin"). The bridge is a
# new module (enh_rst_bridge) which forces a fresh definition with the clock port.

set base_dir [lindex $argv end]
if {$base_dir eq ""} { puts "usage: add_reset_bridge.tcl <base_dir>"; exit 1 }

set rtl {C:/Users/79171/Desktop/FPGA/src/rtl/enh_rst_bridge/enh_rst_bridge.v}

cd $base_dir
open_project {base/base.xpr}
if {[llength [get_files -quiet $rtl]] == 0} { add_files -norecurse $rtl }
update_compile_order -fileset sources_1
open_bd_design {base/base.srcs/sources_1/bd/base/base.bd}

foreach cell {/enh_rst_gate_0 /enh_rst_bridge_0} {
    if {[llength [get_bd_cells -quiet $cell]] > 0} {
        puts "deleting $cell"
        delete_bd_objs [get_bd_cells $cell]
    }
}

foreach n [get_bd_nets -quiet -of_objects [get_bd_pins /enhance_0/ap_rst_n]] {
    puts "clearing [get_property NAME $n] from the kernel reset pin"
    delete_bd_objs $n
}

set bridge [create_bd_cell -type module -reference enh_rst_bridge enh_rst_bridge_0]
puts "created $bridge"

set aresetn_net {rst_ps7_0_fclk1_peripheral_aresetn}
if {[llength [get_bd_nets -quiet $aresetn_net]] == 0} {
    puts "ERROR: $aresetn_net not found"
    exit 1
}
set clk_net [get_property NAME [lindex [get_bd_nets -quiet -of_objects [get_bd_pins /enhance_0/ap_clk]] 0]]
puts "kernel clock net: $clk_net"

set missing {}
foreach pin {aresetn aclk cfg_hi ap_rst_n} {
    if {[llength [get_bd_pins -quiet /enh_rst_bridge_0/$pin]] == 0} { lappend missing $pin }
}
if {[llength $missing] > 0} {
    puts "ERROR: bridge is missing pins: $missing"
    exit 1
}

connect_bd_net -net $aresetn_net [get_bd_pins /enh_rst_bridge_0/aresetn]
connect_bd_net -net $clk_net     [get_bd_pins /enh_rst_bridge_0/aclk]
connect_bd_net [get_bd_pins /gpio_enh_cfg/gpio2_io_o]  [get_bd_pins /enh_rst_bridge_0/cfg_hi]
connect_bd_net [get_bd_pins /enh_rst_bridge_0/ap_rst_n] [get_bd_pins /enhance_0/ap_rst_n]

validate_bd_design
save_bd_design

foreach p [get_bd_pins -quiet /enh_rst_bridge_0/*] {
    set nets [get_bd_nets -quiet -of_objects $p]
    puts "  [get_property NAME $p] -> $nets"
}
puts "RESULT: RESET BRIDGE ADDED"
exit 0
