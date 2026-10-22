# Insert the HLS SOF generator into the repaired block design, in the middle of the interface path.
#
#   vivado -mode batch -source build\overlay_hdmi_enhance\insert_sof_final.tcl
#
# Preconditions checked by the script:
#   * pixel_unpack/stream_out_24 and v_axi4s_vid_out/video_in are already joined by an interface net
#     (repair_bd.tcl restored that), so the net is deleted deliberately and re-laid through the new
#     cell;
#   * the HLS IP is extracted into .work/sof_ip and registered as a repository path.
#
# Verification after wiring: both sides of the kernel must be interface nets, otherwise the overlay
# will not parse even though it synthesises.

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

set unpack [get_bd_cells /video/hdmi_out/pixel_unpack]
set vidout [get_bd_cells /video/hdmi_out/frontend/v_axi4s_vid_out_0]

# --- precondition: the direct interface path must exist --------------------------------
set direct [get_bd_intf_nets -quiet -of_objects [get_bd_intf_pins -quiet $vidout/video_in]]
if {$direct eq ""} {
    puts "ERROR: pixel_unpack -> vid_out is not connected; run repair_bd.tcl first"
    exit 1
}
puts "current stream interface net: $direct"

# --- remove it, then re-lay through the kernel ------------------------------------------
if {[llength [get_bd_cells -quiet /sof_gen_0]] > 0} {
    delete_bd_objs [get_bd_cells /sof_gen_0]
    puts "removed an earlier /sof_gen_0"
}
catch {delete_bd_objs $direct}

create_bd_cell -type ip -vlnv xilinx.com:hls:sof_gen:1.0 /sof_gen_0
set sof [get_bd_cells /sof_gen_0]
puts "created /sof_gen_0"

puts "--- interfaces on /sof_gen_0 ---"
foreach p [get_bd_intf_pins -of_objects $sof] { puts "  [get_property NAME $p]" }

set in_pin  [get_bd_intf_pins -quiet /sof_gen_0/s_in]
set out_pin [get_bd_intf_pins -quiet /sof_gen_0/s_out]
if {$in_pin eq "" || $out_pin eq ""} {
    puts "ERROR: expected s_in / s_out on the kernel"
    save_bd_design
    exit 1
}

set src [get_bd_intf_pins -quiet $unpack/stream_out_24]
set dst [get_bd_intf_pins -quiet $vidout/video_in]
if {[catch {connect_bd_intf_net $src $in_pin} cerr]}  { puts "IN:  $cerr" } else { puts "in ok" }
if {[catch {connect_bd_intf_net $out_pin $dst} cerr]} { puts "OUT: $cerr" } else { puts "out ok" }

if {[catch {connect_bd_net [get_bd_pins $vidout/aclk] [get_bd_pins $sof/ap_clk]} cerr]} {
    puts "CLOCK: $cerr"
}
set rst_pin [get_bd_pins -quiet /sof_gen_0/ap_rst_n]
if {$rst_pin ne ""} {
    set reset_net [get_bd_nets -quiet -of_objects [get_bd_pins $vidout/aresetn]]
    if {$reset_net ne "" && [catch {connect_bd_net $reset_net $rst_pin} cerr] == 0} {
        puts "reset ok"
    } else {
        puts "reset: $cerr"
    }
}

catch {validate_bd_design}
save_bd_design
puts "design saved"

# --- verification ------------------------------------------------------------------------
set ok 1
foreach pin [list $in_pin $out_pin] {
    set n [get_bd_intf_nets -quiet -of_objects $pin]
    puts "  [get_property NAME $pin] -> $n"
    if {$n eq ""} { set ok 0 }
}
if {!$ok} {
    puts "STREAM INTERFACE DANGLING"
    exit 1
}
puts "check: the kernel sits inside an interface path"

reset_target all [get_files -quiet base.bd]
generate_target all [get_files -quiet base.bd] -force
puts "RESULT: SOF INSERTED INTO AN INTERFACE PATH"
exit 0
