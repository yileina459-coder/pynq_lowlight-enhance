# Insert the SOF kernel inside the video hierarchy, where its stream lives.
#
#   vivado -mode batch -source build\overlay_hdmi_enhance\insert_sof_in_hierarchy.tcl
#
# Why inside the hierarchy
#   v_axi4s_vid_out sits at /video/hdmi_out/frontend, so its video_in pin and the pixel_unpack
#   output are joined by a hierarchy-local interface net. Connecting a *top-level* cell to those
#   pins does not produce an interface net - Vivado falls back to pin-level connections, which is
#   exactly what broke PYNQ's metadata parser earlier
#   (MetadataObjectNotFound: s_axis_video_tdata[...]). Creating the cell inside the same hierarchy
#   keeps both hops interface-to-interface.

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

# --- remove the direct hop, which lives inside /video/hdmi_out/frontend -----------------
set dst_top [get_bd_intf_pins -quiet /video/hdmi_out/frontend/v_axi4s_vid_out_0/video_in]
set direct [get_bd_intf_nets -quiet -of_objects $dst_top]
if {$direct ne ""} {
    catch {delete_bd_objs $direct}
    puts "removed the direct interface net ($direct)"
}

current_bd_instance /video/hdmi_out

if {[llength [get_bd_cells -quiet sof_gen_0]] > 0} {
    delete_bd_objs [get_bd_cells sof_gen_0]
    puts "removed an earlier sof_gen_0"
}
create_bd_cell -type ip -vlnv xilinx.com:hls:sof_gen:1.0 sof_gen_0
set sof [get_bd_cells sof_gen_0]
puts "created /video/hdmi_out/sof_gen_0"

set src [get_bd_intf_pins -quiet pixel_unpack/stream_out_24]
set dst [get_bd_intf_pins -quiet frontend/v_axi4s_vid_out_0/video_in]
set in_pin  [get_bd_intf_pins -quiet sof_gen_0/s_in]
set out_pin [get_bd_intf_pins -quiet sof_gen_0/s_out]
if {$src eq "" || $dst eq "" || $in_pin eq "" || $out_pin eq ""} {
    puts "ERROR: pins missing (src='$src' dst='$dst' in='$in_pin' out='$out_pin')"
    current_bd_instance /
    save_bd_design
    exit 1
}

if {[catch {connect_bd_intf_net $src $in_pin} cerr]}  { puts "IN:  $cerr" } else { puts "in connected" }
if {[catch {connect_bd_intf_net $out_pin $dst} cerr]} { puts "OUT: $cerr" } else { puts "out connected" }

# --- clock and reset from the video domain ---------------------------------------------
set vid_clk [get_bd_pins -quiet frontend/v_axi4s_vid_out_0/aclk]
if {$vid_clk ne ""} {
    if {[catch {connect_bd_net $vid_clk [get_bd_pins sof_gen_0/ap_clk]} cerr]} {
        puts "CLOCK: $cerr"
    } else {
        puts "clock connected"
    }
}
set rst_pin [get_bd_pins -quiet sof_gen_0/ap_rst_n]
if {$rst_pin ne ""} {
    set reset_net [get_bd_nets -quiet -of_objects [get_bd_pins frontend/v_axi4s_vid_out_0/aresetn]]
    if {$reset_net ne ""} {
        if {[catch {connect_bd_net $reset_net $rst_pin} cerr]} { puts "RESET: $cerr" } \
        else { puts "reset connected" }
    } else {
        puts "ERROR: no reset net on the video core"
    }
}

current_bd_instance /

catch {validate_bd_design}
save_bd_design
puts "design saved"

# --- verification: interface nets on both sides of the kernel --------------------------
set ok 1
foreach path {/video/hdmi_out/sof_gen_0/s_in /video/hdmi_out/sof_gen_0/s_out} {
    set p [get_bd_intf_pins -quiet $path]
    set n [get_bd_intf_nets -quiet -of_objects $p]
    puts "  $path -> $n"
    if {$n eq ""} { set ok 0 }
}
if {!$ok} {
    puts "RESULT: SOF STREAM DANGLING"
    exit 1
}
puts "RESULT: SOF KERNEL INSERTED AS INTERFACES"
exit 0
