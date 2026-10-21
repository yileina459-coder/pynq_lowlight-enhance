# Re-create the reset gate so the block design picks up the new aclk port.
#
# Same trap as axis_cycle_stamp earlier: a block-design module reference caches its port
# list, so editing the RTL and calling update_module_reference does not add ports. The
# cell has to be deleted and re-created. `clock_the_gate.tcl` failed with "the gate has
# no aclk pin" for exactly this reason.

set base_dir [lindex $argv end]
if {$base_dir eq ""} { puts "usage: rebuild_gate.tcl <base_dir>"; exit 1 }

set rtl {C:/Users/79171/Desktop/FPGA/src/rtl/enh_rst_gate/enh_rst_gate.v}

cd $base_dir
open_project {base/base.xpr}
if {[llength [get_files -quiet $rtl]] == 0} { add_files -norecurse $rtl }
update_compile_order -fileset sources_1
open_bd_design {base/base.srcs/sources_1/bd/base/base.bd}

if {[llength [get_bd_cells -quiet /enh_rst_gate_0]] > 0} {
    puts "deleting the stale gate"
    delete_bd_objs [get_bd_cells /enh_rst_gate_0]
}

set gate [create_bd_cell -type module -reference enh_rst_gate enh_rst_gate_0]
puts "created $gate"

# The kernel reset net is free again (the old gate was its only driver).
set ap_rst_nets [get_bd_nets -quiet -of_objects [get_bd_pins /enhance_0/ap_rst_n]]
foreach n $ap_rst_nets {
    puts "  clearing [get_property NAME $n] from the kernel reset pin"
    delete_bd_objs $n
}

set aresetn_net {rst_ps7_0_fclk1_peripheral_aresetn}
if {[llength [get_bd_nets -quiet $aresetn_net]] == 0} {
    puts "ERROR: $aresetn_net not found"
    exit 1
}

set clk_net [get_property NAME [lindex [get_bd_nets -quiet -of_objects [get_bd_pins /enhance_0/ap_clk]] 0]]
puts "kernel clock net: $clk_net"

connect_bd_net -net $aresetn_net [get_bd_pins /enh_rst_gate_0/aresetn]
connect_bd_net -net $clk_net [get_bd_pins /enh_rst_gate_0/aclk]
connect_bd_net [get_bd_pins /gpio_enh_cfg/gpio2_io_o] [get_bd_pins /enh_rst_gate_0/cfg_hi]
connect_bd_net [get_bd_pins /enh_rst_gate_0/ap_rst_n] [get_bd_pins /enhance_0/ap_rst_n]

validate_bd_design
save_bd_design

foreach p [get_bd_pins -quiet /enh_rst_gate_0/*] {
    set nets [get_bd_nets -quiet -of_objects $p]
    puts "  [get_property NAME $p] -> $nets"
}
puts "RESULT: GATE REBUILT WITH CLOCK"
exit 0
