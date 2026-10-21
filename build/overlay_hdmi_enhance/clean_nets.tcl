# Clean up the nets left behind by deleting the pattern generator, then reconnect the
# HDMI input to the first stamp cell.
#
# Symptom this fixes:
#   CRITICAL WARNING: [BD 41-759] /stamp_in_0/s_axis_tvalid is not connected
#   WARNING: dangling interface net <vpg_0_m_axis>
# Deleting a cell leaves its interface net behind as a dangling object; connecting the
# input to the same pin afterwards attaches to that stale net, so tvalid stays
# unconnected and Vivado ties it to 0 - which silently kills the whole video path.

set base_dir [lindex $argv end]
if {$base_dir eq ""} { puts "usage: clean_nets.tcl <base_dir>"; exit 1 }

cd $base_dir
open_project {base/base.xpr}
open_bd_design {base/base.srcs/sources_1/bd/base/base.bd}

# Drop every net that mentions the pattern generator.
foreach net [get_bd_intf_nets -quiet -filter {NAME =~ "*vpg*"}] {
    puts "deleting dangling interface net [get_property NAME $net]"
    delete_bd_objs $net
}
foreach net [get_bd_nets -quiet -filter {NAME =~ "*vpg*"}] {
    puts "deleting dangling net [get_property NAME $net]"
    delete_bd_objs $net
}

# Make sure stamp_in_0/s_axis has exactly one source.
set nets [get_bd_intf_nets -quiet -of_objects [get_bd_intf_pins stamp_in_0/s_axis]]
puts "nets on stamp_in_0/s_axis: $nets"
foreach net $nets {
    puts "  removing [get_property NAME $net]"
    delete_bd_objs $net
}
connect_bd_intf_net [get_bd_intf_pins video/hdmi_in/out_stream] \
                    [get_bd_intf_pins stamp_in_0/s_axis]
puts "reconnected video/hdmi_in/out_stream -> stamp_in_0/s_axis"

validate_bd_design
save_bd_design

# Report any remaining unconnected inputs so the run is not lost silently.
set problems 0
foreach pin [get_bd_pins -quiet -of_objects [get_bd_cells /stamp_in_0]] {
    if {[get_property DIR $pin] eq "I"} {
        set nets [get_bd_nets -quiet -of_objects $pin]
        if {[llength $nets] == 0} {
            puts "WARNING: still unconnected: $pin"
            incr problems
        }
    }
}
puts "RESULT: CLEANED ($problems unconnected inputs remain)"
exit 0
