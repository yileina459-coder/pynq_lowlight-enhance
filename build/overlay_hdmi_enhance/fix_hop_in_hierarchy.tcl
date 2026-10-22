# Close the last stream hop from inside the video hierarchy.
#
#   vivado -mode batch -source build\overlay_hdmi_enhance\fix_hop_in_hierarchy.tcl
#
# The obstacle is that the phantom net is hierarchy-local: its name has no leading slash
# ('pixel_unpack_stream_out_24'), so a top-level get_bd_intf_nets cannot see or delete it, while
# connect_bd_intf_net at top level still refuses because that pin reports itself as connected.
# Entering /video/hdmi_out makes the net visible; the pins are then referenced relative to that
# hierarchy.

set script_dir [file dirname [file normalize [info script]]]
set proj_file  [file join $script_dir ".work" "tree" "boards" "Pynq-Z2" "base" "base" "base.xpr"]

open_project $proj_file
open_bd_design [get_files -quiet base.bd]

current_bd_instance /video/hdmi_out

puts "--- interface nets inside /video/hdmi_out ---"
foreach net [get_bd_intf_nets -quiet] {
    puts "   $net :: [llength [get_bd_intf_pins -quiet -of_objects $net]] pin(s)"
}

set victim [get_bd_intf_nets -quiet pixel_unpack_stream_out_24]
if {$victim ne ""} {
    catch {delete_bd_objs $victim}
    puts "deleted $victim"
}

set src [get_bd_intf_pins -quiet pixel_unpack/stream_out_24]
set dst [get_bd_intf_pins -quiet frontend/v_axi4s_vid_out_0/video_in]
if {$src eq "" || $dst eq ""} {
    puts "ERROR: pins missing inside the hierarchy (src='$src' dst='$dst')"
    current_bd_instance /
    exit 1
}

if {[catch {connect_bd_intf_net $src $dst} cerr]} {
    puts "CONNECT FAILED: $cerr"
} else {
    puts "connected pixel_unpack/stream_out_24 -> frontend/v_axi4s_vid_out_0/video_in"
}

current_bd_instance /

catch {validate_bd_design}
save_bd_design
puts "design saved"

set ok 1
foreach path {/video/hdmi_out/frontend/v_axi4s_vid_out_0/video_in
              /enhance_cfg_0/s_in /enhance_cfg_0/s_out} {
    set p [get_bd_intf_pins -quiet $path]
    set n [get_bd_intf_nets -quiet -of_objects $p]
    puts "  $path -> $n"
    if {$n eq ""} { set ok 0 }
}
if {!$ok} {
    puts "RESULT: STREAMS INCOMPLETE"
    exit 1
}
puts "RESULT: ALL STREAM INTERFACES CONNECTED"
exit 0
