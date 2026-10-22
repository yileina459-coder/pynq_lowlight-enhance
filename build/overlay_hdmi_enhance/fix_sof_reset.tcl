# Connect the SOF generator's reset to whatever net drives v_axi4s_vid_out's reset.
#
#   vivado -mode batch -source build\overlay_hdmi_enhance\fix_sof_reset.tcl
#
# The insertion script left /sof_gen_0/aresetn dangling (BD 41-759): its guess at the reset pin
# path did not match, and a module with an unconnected asynchronous reset is unpredictable.
# Reading the net off the vid_out's own reset pin removes the guesswork.

set script_dir [file dirname [file normalize [info script]]]
set proj_file  [file join $script_dir ".work" "tree" "boards" "Pynq-Z2" "base" "base" "base.xpr"]

open_project $proj_file
open_bd_design [get_files -quiet base.bd]

set sof    [get_bd_cells -quiet /sof_gen_0]
set vidout [get_bd_cells -quiet /video/hdmi_out/frontend/v_axi4s_vid_out_0]
if {$sof eq "" || $vidout eq ""} {
    puts "ERROR: missing cells"
    exit 1
}

set src_pin [get_bd_pins -quiet $vidout/aresetn]
if {$src_pin eq ""} {
    puts "vid_out has no aresetn; pins are:"
    foreach p [get_bd_pins -of_objects $vidout] {
        puts "  [get_property NAME $p] [get_property DIR $p]"
    }
    exit 1
}

set reset_net [get_bd_nets -quiet -of_objects $src_pin]
puts "vid_out reset pin uses net: $reset_net"

if {$reset_net eq ""} {
    # The pin is tied to a constant; reuse the same source.
    set driver [get_bd_pins -quiet -of_objects $reset_net]
    puts "looking for a driver for $src_pin"
    foreach p [get_bd_pins -quiet -of_objects $src_pin] {
        puts "  candidate: $p"
    }
    puts "ERROR: reset pin has no net; wire it manually"
    exit 1
}

set existing [get_bd_nets -quiet -of_objects [get_bd_pins $sof/aresetn]]
if {$existing ne ""} {
    catch {delete_bd_objs $existing}
}
connect_bd_net $reset_net [get_bd_pins $sof/aresetn]
puts "connected /sof_gen_0/aresetn to $reset_net"

validate_bd_design
save_bd_design
reset_target all [get_files -quiet base.bd]
generate_target all [get_files -quiet base.bd] -force

# Confirm nothing in the SOF generator is left floating.
set dangling {}
foreach p [get_bd_pins -of_objects $sof] {
    if {[get_property DIR $p] ne "I"} { continue }
    if {[get_bd_nets -quiet -of_objects $p] eq ""} {
        lappend dangling [get_property NAME $p]
    }
}
if {[llength $dangling] > 0} {
    puts "STILL DANGLING: $dangling"
    exit 1
}
puts "check: every input of /sof_gen_0 is driven"
puts "RESULT: SOF RESET CONNECTED"
exit 0
