# Wire the beat counters into the pattern overlay and rebuild it.
#
# The question this answers: does anything continuously consume the pixel stream?
# first_cycle is latched once, so it cannot distinguish a running pipeline from one
# that stalled after a handful of beats - which is exactly the ambiguity left after
# the capture card showed no TMDS from our overlay.
#
# Channel 1 of gpio_lat now carries stamp_in/beats and channel 2 stamp_out/beats.
# Reading both twice a second apart:
#   * both counting  -> pixels flow into the kernel and out of it
#   * in counting, out frozen -> the kernel or the output stage is back-pressuring

set base_dir [lindex $argv end]

if {$base_dir eq ""} {
    puts "usage: rewire_beats.tcl <base_dir>"
    exit 1
}

cd $base_dir
open_project {base/base.xpr}

set rtl {C:/Users/79171/Desktop/FPGA/src/rtl/axis_cycle_stamp/axis_cycle_stamp.v}
if {[llength [get_files -quiet $rtl]] == 0} {
    add_files -norecurse $rtl
}
update_compile_order -fileset sources_1

open_bd_design {base/base.srcs/sources_1/bd/base/base.bd}

# The module reference must pick up the new `beats` port. Re-creating the cells
# would mean rewiring the stream, so ask Vivado to refresh the references instead.
set stamps [get_bd_cells -hierarchical -filter {NAME =~ "*stamp*"}]
puts "stamp cells: $stamps"
foreach cell $stamps {
    if {[catch {update_module_reference -quiet $cell} err]} {
        puts "update_module_reference on $cell: $err"
    }
}

# Rewire gpio_lat: beats in on channel 1, beats out on channel 2.
set cfg [get_bd_cells -hierarchical -filter {NAME =~ "*lat*"}]
if {[llength $cfg] == 0} {
    puts "ERROR: latency gpio not found"
    exit 1
}
set lat [lindex $cfg 0]

foreach pin [list ${lat}/gpio_io_i ${lat}/gpio2_io_i] {
    foreach net [get_bd_nets -quiet -of_objects [get_bd_pins $pin]] {
        puts "disconnecting $pin from [get_property NAME $net]"
        delete_bd_objs $net
    }
}

set in_net  [get_bd_nets -quiet -of_objects [get_bd_pins ${lat}/gpio_io_i]]
set stamp_in_cell  ""
set stamp_out_cell ""
foreach cell $stamps {
    if {[string match "*stamp_in*" $cell]}  { set stamp_in_cell  $cell }
    if {[string match "*stamp_out*" $cell]} { set stamp_out_cell $cell }
}

puts "stamp_in : $stamp_in_cell"
puts "stamp_out: $stamp_out_cell"

connect_bd_net [get_bd_pins ${stamp_in_cell}/beats]  [get_bd_pins ${lat}/gpio_io_i]
connect_bd_net [get_bd_pins ${stamp_out_cell}/beats] [get_bd_pins ${lat}/gpio2_io_i]

assign_bd_address
validate_bd_design
save_bd_design

puts "RESULT: BEATS REWIRED"
exit 0
