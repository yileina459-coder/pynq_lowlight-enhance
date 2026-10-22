# Remove the SOF cell and restore the direct pixel_unpack -> v_axi4s_vid_out interface hop.
#
#   vivado -mode batch -source build\overlay_hdmi_enhance\undo_sof_hierarchy.tcl
#
# Run this whenever an insertion attempt leaves the cell half wired: a dangling stream input still
# synthesises, so the design would build into a bitstream that cannot produce a picture.

set script_dir [file dirname [file normalize [info script]]]
set proj_file  [file join $script_dir ".work" "tree" "boards" "Pynq-Z2" "base" "base" "base.xpr"]

open_project $proj_file
open_bd_design [get_files -quiet base.bd]

current_bd_instance /video/hdmi_out
set sof [get_bd_cells -quiet sof_gen_0]
if {$sof ne ""} {
    delete_bd_objs [get_bd_cells sof_gen_0]
    puts "deleted /video/hdmi_out/sof_gen_0"
}

# Reconnect the direct hop, clearing whatever phantom net still claims the source pin.
set src [get_bd_intf_pins -quiet pixel_unpack/stream_out_24]
set dst [get_bd_intf_pins -quiet frontend/v_axi4s_vid_out_0/video_in]
foreach net [get_bd_intf_nets -quiet] {
    set pins [get_bd_intf_pins -quiet -of_objects $net]
    if {[lsearch -exact $pins $src] >= 0 || [lsearch -exact $pins $dst] >= 0 || [llength $pins] == 0} {
        catch {delete_bd_objs $net}
        puts "cleared $net"
    }
}
# Hierarchy-local leftovers.
foreach name {pixel_unpack_stream_out_24 Conn3} {
    set n [get_bd_intf_nets -quiet $name]
    if {$n ne ""} { catch {delete_bd_objs $n}; puts "cleared $name" }
}

if {[catch {connect_bd_intf_net $src $dst} cerr]} {
    puts "CONNECT FAILED: $cerr"
} else {
    puts "restored pixel_unpack/stream_out_24 -> frontend/v_axi4s_vid_out_0/video_in"
}

current_bd_instance /

catch {validate_bd_design}
save_bd_design
puts "design saved"

set n [get_bd_intf_nets -quiet -of_objects [get_bd_intf_pins -quiet /video/hdmi_out/frontend/v_axi4s_vid_out_0/video_in]]
if {$n eq ""} {
    puts "RESULT: STREAM STILL BROKEN"
    exit 1
}
puts "  video_in -> $n"
puts "RESULT: DIRECT STREAM RESTORED"
exit 0
