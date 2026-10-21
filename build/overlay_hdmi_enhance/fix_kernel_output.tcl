# Connect the kernel's output side, which the earlier wiring silently missed.
#
# The wiring loop looked up pins as "$kernel/s_out_$suffix" with lowercase suffixes
# (tdata, tvalid, ...). This IP exposes them as s_out_TDATA, s_out_TVALID, ... - and because
# the lookup used -quiet, every miss was silent. The input side happened to be right, so the
# design validated, built and produced a bitstream whose kernel output went nowhere:
#
#     PIN s_out_TDATA DIR=O NET=/enhance_cfg_0_s_out_TDATA
#
# A net named after the pin itself means the pin is dangling. The board symptom was a
# completely dead picture: writeframe() never returned because the VDMA never completed a
# frame, since nothing downstream of the kernel was ever connected.
#
# This script resolves each pin by trying both spellings and reports what it connected, so a
# miss cannot be silent again.

set script_dir [file dirname [file normalize [info script]]]
set proj_file  [file join $script_dir ".work" "tree" "boards" "Pynq-Z2" "base" "base" "base.xpr"]

open_project $proj_file
open_bd_design [get_files -quiet base.bd]

set kernel    [get_bd_cells /enhance_cfg_0]
set stamp_out [get_bd_cells /stamp_out_0]

set suffixes {tdata tvalid tready tkeep tstrb tuser tlast tid tdest}
set connected 0
set missing {}

foreach suffix $suffixes {
    # The kernel's pins are upper-case, the RTL module's are lower-case.
    set upper [string toupper $suffix]
    set src ""
    foreach candidate [list $kernel/s_out_$upper $kernel/s_out_$suffix] {
        set pin [get_bd_pins -quiet $candidate]
        if {$pin ne ""} { set src $pin; break }
    }
    set dst [get_bd_pins -quiet $stamp_out/s_axis_$suffix]
    if {$src eq "" || $dst eq ""} {
        lappend missing "s_out_$suffix (src=$src dst=$dst)"
        continue
    }
    set existing [get_bd_nets -quiet -of_objects $dst]
    if {$existing ne "" && [get_bd_nets -quiet -of_objects $src] eq $existing} {
        puts "already connected: s_out_$upper -> stamp_out_0/s_axis_$suffix"
        incr connected
        continue
    }
    connect_bd_net $src $dst
    set net [get_bd_nets -quiet -of_objects $dst]
    puts "connected: s_out_$upper -> stamp_out_0/s_axis_$suffix  (net $net)"
    incr connected
}

puts "connected $connected of [llength $suffixes] output pins"
if {[llength $missing] > 0} {
    puts "MISSING: $missing"
    exit 1
}

validate_bd_design
save_bd_design

reset_target all [get_files -quiet base.bd]
generate_target all [get_files -quiet base.bd] -force
puts "output products regenerated"

# Prove the output side is no longer dangling: every s_out_* pin must share a net with a
# stamp pin, i.e. the net name must not be the pin's own name.
set dangling {}
foreach p [get_bd_pins -of_objects $kernel] {
    set name [get_property NAME $p]
    if {![string match "s_out_*" $name]} { continue }
    set net [get_bd_nets -quiet -of_objects $p]
    if {$net eq "" || $net eq "/$name"} {
        lappend dangling $name
    }
}
if {[llength $dangling] > 0} {
    puts "STILL DANGLING: $dangling"
    exit 1
}
puts "check: no dangling s_out_* pins"

puts "RESULT: OUTPUT SIDE CONNECTED"
exit 0
