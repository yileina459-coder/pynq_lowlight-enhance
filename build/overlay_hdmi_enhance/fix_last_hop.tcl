# Remove orphan interface nets, then join pixel_unpack to v_axi4s_vid_out.
#
#   vivado -mode batch -source build\overlay_hdmi_enhance\fix_last_hop.tcl
#
# connect_bd_intf_net reports "interface pin 'stream_out_24' is already connected to interface net
# 'pixel_unpack_stream_out_24'", but neither pin of that net is actually attached to anything: the
# net survived the cell deletions as an orphan object. Deleting every interface net with no pins,
# then connecting the two ends, is what clears it.

set script_dir [file dirname [file normalize [info script]]]
set proj_file  [file join $script_dir ".work" "tree" "boards" "Pynq-Z2" "base" "base" "base.xpr"]

open_project $proj_file
open_bd_design [get_files -quiet base.bd]

set orphans {}
foreach net [get_bd_intf_nets -quiet] {
    if {[llength [get_bd_intf_pins -quiet -of_objects $net]] == 0} {
        lappend orphans $net
    }
}
puts "orphan interface nets: $orphans"
foreach net $orphans {
    catch {delete_bd_objs $net}
}
puts "orphans removed"

set src [get_bd_intf_pins -quiet /video/hdmi_out/pixel_unpack/stream_out_24]
set dst [get_bd_intf_pins -quiet /video/hdmi_out/frontend/v_axi4s_vid_out_0/video_in]
if {$src eq "" || $dst eq ""} {
    puts "ERROR: pins missing (src='$src' dst='$dst')"
    save_bd_design
    exit 1
}

if {[catch {connect_bd_intf_net $src $dst} cerr]} {
    puts "CONNECT FAILED: $cerr"
} else {
    puts "connected pixel_unpack/stream_out_24 -> vid_out/video_in"
}

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
