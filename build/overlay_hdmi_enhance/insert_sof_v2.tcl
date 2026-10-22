# Insert the SOF kernel in the hierarchy that owns the stream - second attempt, clean state.
#
#   vivado -mode batch -source build\overlay_hdmi_enhance\insert_sof_v2.tcl
#
# Preconditions (verified below, and the script aborts if they fail):
#   * pixel_unpack/stream_out_24 is joined to frontend/v_axi4s_vid_out_0/video_in by an interface
#     net, i.e. the design is in the repaired state;
#   * that net is the only thing on those pins.
#
# The previous attempt failed on s_in because the source pin still claimed to be connected to a
# phantom hierarchy-local net; that net was removed by undo_sof_hierarchy.tcl, so the same
# connection is expected to succeed here.

set script_dir [file dirname [file normalize [info script]]]
set proj_file  [file join $script_dir ".work" "tree" "boards" "Pynq-Z2" "base" "base" "base.xpr"]
set ip_repo    [file join $script_dir ".work" "sof_ip"]

open_project $proj_file
set existing [get_property IP_REPO_PATHS [current_project]]
if {[lsearch -exact $existing $ip_repo] < 0} {
    set_property IP_REPO_PATHS [concat $existing $ip_repo] [current_project]
    update_ip_catalog -rebuild
}
open_bd_design [get_files -quiet base.bd]

# --- precondition -----------------------------------------------------------------------
set dst_top [get_bd_intf_pins -quiet /video/hdmi_out/frontend/v_axi4s_vid_out_0/video_in]
set direct  [get_bd_intf_nets -quiet -of_objects $dst_top]
if {$direct eq ""} {
    puts "ERROR: the direct hop is missing; run undo_sof_hierarchy.tcl first"
    exit 1
}
puts "direct hop currently: $direct"

# --- open the hop -----------------------------------------------------------------------
if {[catch {delete_bd_objs $direct} cerr]} {
    puts "ERROR: could not delete the direct net: $cerr"
    exit 1
}
puts "removed $direct"

# --- create the cell inside the stream's own hierarchy -----------------------------------
current_bd_instance /video/hdmi_out

if {[llength [get_bd_cells -quiet sof_gen_0]] > 0} {
    delete_bd_objs [get_bd_cells sof_gen_0]
}
create_bd_cell -type ip -vlnv xilinx.com:hls:sof_gen:1.0 sof_gen_0
puts "created /video/hdmi_out/sof_gen_0"

set src     [get_bd_intf_pins -quiet pixel_unpack/stream_out_24]
set dst     [get_bd_intf_pins -quiet frontend/v_axi4s_vid_out_0/video_in]
set in_pin  [get_bd_intf_pins -quiet sof_gen_0/s_in]
set out_pin [get_bd_intf_pins -quiet sof_gen_0/s_out]

set ok 1
if {[catch {connect_bd_intf_net $src $in_pin} cerr]} {
    puts "IN FAILED: $cerr"
    set ok 0
} else {
    puts "in connected"
}
if {[catch {connect_bd_intf_net $out_pin $dst} cerr]} {
    puts "OUT FAILED: $cerr"
    set ok 0
} else {
    puts "out connected"
}

# clock and reset from the video core
if {[catch {connect_bd_net [get_bd_pins frontend/v_axi4s_vid_out_0/aclk] \
                          [get_bd_pins sof_gen_0/ap_clk]} cerr]} { puts "CLOCK: $cerr" } \
else { puts "clock connected" }
set rst_pin [get_bd_pins -quiet sof_gen_0/ap_rst_n]
set reset_net [get_bd_nets -quiet -of_objects [get_bd_pins frontend/v_axi4s_vid_out_0/aresetn]]
if {$rst_pin ne "" && $reset_net ne ""} {
    if {[catch {connect_bd_net $reset_net $rst_pin} cerr]} { puts "RESET: $cerr" } \
    else { puts "reset connected" }
}

current_bd_instance /

if {$ok == 0} {
    puts "insertion incomplete; the design is left with an open hop - rerun undo_sof_hierarchy.tcl"
    exit 1
}

catch {validate_bd_design}
save_bd_design
puts "design saved"

foreach path {/video/hdmi_out/sof_gen_0/s_in /video/hdmi_out/sof_gen_0/s_out} {
    set p [get_bd_intf_pins -quiet $path]
    puts "  $path -> [get_bd_intf_nets -quiet -of_objects $p]"
}
puts "RESULT: SOF INSERTED IN HIERARCHY"
exit 0
