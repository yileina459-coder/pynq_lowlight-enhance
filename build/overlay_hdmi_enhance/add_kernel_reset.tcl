# Insert a PS-controlled reset gate in front of the kernel's ap_rst_n.
#
# Background (see src/rtl/enh_rst_gate/enh_rst_gate.v): the kernel is free-running, so
# HLS samples its loop-invariant configuration once in the pipeline prologue. Six of the
# nine parameters are therefore frozen at power-up and ignore later writes. Pulsing the
# kernel reset re-runs the prologue and re-samples them.
#
# The gate uses bit 31 of the second configuration word as the request, because
# enh_cfg_split only consumes bits 26:0 of that word - so the PS can toggle it without
# touching any real parameter.
#
# Rewiring note: `disconnect_bd_net` refused the call ("Missing value for option
# 'objects'"), so the shared reset net is rebuilt instead - delete it, reconnect every
# original sink except the kernel, then add the gate. That keeps the other peripherals
# on the same reset domain.

set base_dir [lindex $argv end]
if {$base_dir eq ""} { puts "usage: add_kernel_reset.tcl <base_dir>"; exit 1 }

set rtl {C:/Users/79171/Desktop/FPGA/src/rtl/enh_rst_gate/enh_rst_gate.v}

cd $base_dir
open_project {base/base.xpr}
if {[llength [get_files -quiet $rtl]] == 0} {
    add_files -norecurse $rtl
    puts "added $rtl"
}
update_compile_order -fileset sources_1
open_bd_design {base/base.srcs/sources_1/bd/base/base.bd}

set ap_rst_pin [get_bd_pins -quiet /enhance_0/ap_rst_n]
if {[llength $ap_rst_pin] == 0} { puts "ERROR: enhance_0/ap_rst_n missing"; exit 1 }

set old_nets [get_bd_nets -quiet -of_objects $ap_rst_pin]
if {[llength $old_nets] == 0} { puts "ERROR: kernel reset has no net"; exit 1 }
set net_name [get_property NAME [lindex $old_nets 0]]
puts "kernel reset net: $net_name"

# Snapshot every pin on that net before rebuilding it.
set all_pins [get_bd_pins -quiet -of_objects [lindex $old_nets 0]]
# get_property NAME returns the short pin name ("ap_rst_n"), so comparing against the
# full path silently kept the kernel pin; the reconnect then failed with "sink is
# already connected to another source". Check the owning cell as well.
set keep {}
foreach p $all_pins {
    set short [get_property NAME $p]
    set cell  [get_bd_cells -quiet -of_objects $p]
    set owner [expr {[llength $cell] ? [get_property NAME [lindex $cell 0]] : ""}]
    if {$short eq "ap_rst_n" && $owner eq "enhance_0"} {
        puts "  skipping $owner/$short (the kernel pin)"
        continue
    }
    lappend keep $p
}
puts "net has [llength $all_pins] pins; keeping [llength $keep] of them"

delete_bd_objs [lindex $old_nets 0]
puts "deleted $net_name"

foreach p $keep {
    connect_bd_net -net $net_name $p
}
puts "rebuilt $net_name without the kernel pin"

if {[llength [get_bd_cells -quiet /enh_rst_gate_0]] == 0} {
    create_bd_cell -type module -reference enh_rst_gate enh_rst_gate_0
    puts "created enh_rst_gate_0"
}

connect_bd_net -net $net_name [get_bd_pins /enh_rst_gate_0/aresetn]
connect_bd_net [get_bd_pins /gpio_enh_cfg/gpio2_io_o] [get_bd_pins /enh_rst_gate_0/cfg_hi]
connect_bd_net [get_bd_pins /enh_rst_gate_0/ap_rst_n] [get_bd_pins /enhance_0/ap_rst_n]
puts "gated: aresetn & ~cfg_hi[31] -> enhance_0/ap_rst_n"

validate_bd_design
save_bd_design

# Report the result so a silent failure cannot waste a build.
foreach p [get_bd_pins -quiet /enh_rst_gate_0/*] {
    set nets [get_bd_nets -quiet -of_objects $p]
    puts "  [get_property NAME $p] -> $nets"
}
puts "RESULT: KERNEL RESET GATE ADDED"
exit 0
