# Finish the SOF interface wiring: connect the kernel's stream output to the video core.
#
#   vivado -mode batch -source build\overlay_hdmi_enhance\finish_sof_hls.tcl
#
# create_bd_cell auto-connected the input side (the design already has a matching interface net),
# so only the output side is left. The interface names come from the HLS IP: S_AXIS / M_AXIS.

set script_dir [file dirname [file normalize [info script]]]
set proj_file  [file join $script_dir ".work" "tree" "boards" "Pynq-Z2" "base" "base" "base.xpr"]

open_project $proj_file
open_bd_design [get_files -quiet base.bd]

set sof [get_bd_cells -quiet /sof_gen_0]
if {$sof eq ""} { puts "ERROR: /sof_gen_0 missing"; exit 1 }

puts "--- interface pins of /sof_gen_0 ---"
foreach p [get_bd_intf_pins -of_objects $sof] {
    puts "  [get_property NAME $p] net=[get_bd_intf_nets -quiet -of_objects $p]"
}

set vidout [get_bd_cells /video/hdmi_out/frontend/v_axi4s_vid_out_0]
set out_pin ""
foreach candidate {/sof_gen_0/M_AXIS /sof_gen_0/m_axis /sof_gen_0/s_out} {
    set p [get_bd_intf_pins -quiet $candidate]
    if {$p ne ""} { set out_pin $p; break }
}
if {$out_pin eq ""} { puts "ERROR: no stream output interface on /sof_gen_0"; exit 1 }

set dst [get_bd_intf_pins -quiet $vidout/video_in]
if {$dst eq ""} {
    puts "--- interfaces of vid_out ---"
    foreach p [get_bd_intf_pins -of_objects $vidout] { puts "  [get_property NAME $p]" }
    exit 1
}

set existing [get_bd_intf_nets -quiet -of_objects $dst]
if {$existing ne ""} {
    puts "note: the video core input already has interface net '$existing'"
    set src_of_net [get_bd_intf_pins -quiet -of_objects $existing]
    puts "      its members: $src_of_net"
}

if {[catch {connect_bd_intf_net $out_pin $dst} cerr]} {
    puts "CONNECT FAILED: $cerr"
} else {
    puts "connected $out_pin -> $vidout/video_in"
}

# clock / reset
if {[catch {connect_bd_net [get_bd_pins $vidout/aclk] [get_bd_pins $sof/ap_clk]} cerr]} {
    puts "clock: $cerr"
}
set rst_pin [get_bd_pins -quiet /sof_gen_0/ap_rst_n]
if {$rst_pin ne ""} {
    set reset_net [get_bd_nets -quiet -of_objects [get_bd_pins $vidout/aresetn]]
    if {$reset_net ne ""} {
        if {[catch {connect_bd_net $reset_net $rst_pin} cerr]} { puts "reset: $cerr" } \
        else { puts "reset connected" }
    }
}

validate_bd_design
save_bd_design

set ok 1
foreach pin {/sof_gen_0/S_AXIS /sof_gen_0/M_AXIS} {
    set p [get_bd_intf_pins -quiet $pin]
    if {$p eq ""} { continue }
    set n [get_bd_intf_nets -quiet -of_objects $p]
    puts "  $pin -> $n"
    if {$n eq ""} { set ok 0 }
}
if {!$ok} { puts "STREAM INTERFACE STILL DANGLING"; exit 1 }
puts "check: both stream sides are interface connections"

reset_target all [get_files -quiet base.bd]
generate_target all [get_files -quiet base.bd] -force
puts "RESULT: SOF HLS WIRING COMPLETE"
exit 0
