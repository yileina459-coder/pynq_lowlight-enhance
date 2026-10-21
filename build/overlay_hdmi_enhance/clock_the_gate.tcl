# Connect the kernel clock to the reset gate.
#
# enh_rst_gate now re-times the de-assertion of ap_rst_n through the kernel's own clock
# domain (async assert, sync release), because driving the reset straight from the
# 100 MHz PS-domain comparison let the pipeline start on an arbitrary clock phase - on
# the board that surfaced as one preset flickering continuously.

set base_dir [lindex $argv end]
if {$base_dir eq ""} { puts "usage: clock_the_gate.tcl <base_dir>"; exit 1 }

cd $base_dir
open_project {base/base.xpr}
open_bd_design {base/base.srcs/sources_1/bd/base/base.bd}

set gate [get_bd_cells -quiet /enh_rst_gate_0]
if {[llength $gate] == 0} { puts "ERROR: enh_rst_gate_0 missing"; exit 1 }

set clk_net [get_property NAME [lindex [get_bd_nets -quiet -of_objects [get_bd_pins /enhance_0/ap_clk]] 0]]
puts "kernel clock net: $clk_net"

set aclk_pin [get_bd_pins -quiet /enh_rst_gate_0/aclk]
if {[llength $aclk_pin] == 0} {
    puts "ERROR: the gate has no aclk pin - the RTL was not re-imported"
    exit 1
}
connect_bd_net -net $clk_net $aclk_pin
puts "connected $clk_net -> /enh_rst_gate_0/aclk"

validate_bd_design
save_bd_design

foreach p [get_bd_pins -quiet /enh_rst_gate_0/*] {
    set nets [get_bd_nets -quiet -of_objects $p]
    puts "  [get_property NAME $p] -> $nets"
}
puts "RESULT: GATE CLOCKED"
exit 0
