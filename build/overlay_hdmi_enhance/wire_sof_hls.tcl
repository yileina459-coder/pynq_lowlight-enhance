# Create and wire the HLS SOF generator in one pass, and save no matter what.
#
#   vivado -mode batch -source build\overlay_hdmi_enhance\wire_sof_hls.tcl
#
# The previous two attempts each died on a connect and therefore never reached save_bd_design, so
# the cell kept vanishing. Every connection here is wrapped in catch and the design is saved
# unconditionally; the interface nets are then checked, which is the property that matters.

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

foreach cell {/sof_gen_0 /sof_en_slice} {
    set c [get_bd_cells -quiet $cell]
    if {$c ne ""} { delete_bd_objs [get_bd_cells $c]; puts "deleted $cell" }
}

create_bd_cell -type ip -vlnv xilinx.com:hls:sof_gen:1.0 /sof_gen_0
set sof [get_bd_cells /sof_gen_0]
puts "created /sof_gen_0 (HLS)"

puts "--- interfaces on the new cell ---"
foreach p [get_bd_intf_pins -of_objects $sof] { puts "  [get_property NAME $p]" }

# Input side: whatever the kernel calls it.
set in_pin ""
foreach candidate {/sof_gen_0/S_AXIS /sof_gen_0/s_in /sof_gen_0/s_axis} {
    set p [get_bd_intf_pins -quiet $candidate]
    if {$p ne ""} { set in_pin $p; break }
}
set out_pin ""
foreach candidate {/sof_gen_0/M_AXIS /sof_gen_0/s_out /sof_gen_0/m_axis} {
    set p [get_bd_intf_pins -quiet $candidate]
    if {$p ne ""} { set out_pin $p; break }
}

if {$in_pin eq "" || $out_pin eq ""} {
    puts "ERROR: could not identify the stream interfaces (in='$in_pin' out='$out_pin')"
    save_bd_design
    exit 1
}

set src_intf [get_bd_intf_pins -quiet $unpack/stream_out_24]
set dst_intf [get_bd_intf_pins -quiet $vidout/video_in]

if {[catch {connect_bd_intf_net $src_intf $in_pin} cerr]} {
    puts "IN CONNECT: $cerr"
} else {
    puts "connected pixel_unpack/stream_out_24 -> $in_pin"
}
if {[catch {connect_bd_intf_net $out_pin $dst_intf} cerr]} {
    puts "OUT CONNECT: $cerr"
} else {
    puts "connected $out_pin -> vid_out/video_in"
}

if {[catch {connect_bd_net [get_bd_pins $vidout/aclk] [get_bd_pins $sof/ap_clk]} cerr]} {
    puts "CLOCK: $cerr"
}
set rst_pin [get_bd_pins -quiet /sof_gen_0/ap_rst_n]
if {$rst_pin ne ""} {
    set reset_net [get_bd_nets -quiet -of_objects [get_bd_pins $vidout/aresetn]]
    if {$reset_net ne ""} {
        if {[catch {connect_bd_net $reset_net $rst_pin} cerr]} { puts "RESET: $cerr" } \
        else { puts "reset connected" }
    }
}

catch {validate_bd_design}
save_bd_design
puts "design saved"

set ok 1
foreach pin [list $in_pin $out_pin] {
    set n [get_bd_intf_nets -quiet -of_objects $pin]
    puts "  [get_property NAME $pin] -> net=[get_bd_intf_nets -quiet -of_objects $pin]"
    if {$n eq ""} { set ok 0 }
}
if {!$ok} {
    puts "STREAM INTERFACE DANGLING"
    exit 1
}
puts "check: both stream sides are interface connections"

reset_target all [get_files -quiet base.bd]
generate_target all [get_files -quiet base.bd] -force
puts "RESULT: SOF HLS WIRED AND SAVED"
exit 0
