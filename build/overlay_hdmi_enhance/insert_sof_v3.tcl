# Insert the SOF generator into the video hierarchy, where the stream interface actually lives.
#
#   vivado -mode batch -source build\overlay_hdmi_enhance\insert_sof_v3.tcl
#
# Lesson from the earlier attempts: v_axi4s_vid_out sits at /video/hdmi_out/frontend, so its video_in
# pin is joined to pixel_unpack by a *hierarchy-local* interface net. A top-level cell cannot be
# inserted into that hop - Vivado silently falls back to pin-level connections, which is exactly what
# PYNQ's .hwh parser rejects. The cell therefore has to be created inside /video/hdmi_out, and the
# connections made relative to that hierarchy.
#
# The script prints the interface state before and after, because create_bd_cell sometimes auto-
# connects a matching interface, and blindly connecting again fails with
# "interface pin/port 'x' is already connected".

set script_dir [file dirname [file normalize [info script]]]
set proj_file  [file join $script_dir ".work" "tree" "boards" "Pynq-Z2" "base" "base" "base.xpr"]
set sof_repo   [file join $script_dir ".work" "sof_ip"]

open_project $proj_file

set paths [get_property IP_REPO_PATHS [current_project]]
if {[lsearch -exact $paths $sof_repo] < 0} {
    set_property IP_REPO_PATHS [concat $paths $sof_repo] [current_project]
    update_ip_catalog -rebuild
    puts "registered the SOF IP repository"
}

open_bd_design [get_files -quiet base.bd]
current_bd_instance /video/hdmi_out

# --- state before ------------------------------------------------------------------------
set unpack [get_bd_cells -quiet pixel_unpack]
set frontend [get_bd_cells -quiet frontend]
set vidout [get_bd_cells -quiet frontend/v_axi4s_vid_out_0]
if {$unpack eq "" || $vidout eq ""} {
    puts "ERROR: cannot find pixel_unpack or v_axi4s_vid_out inside /video/hdmi_out"
    current_bd_instance /
    exit 1
}

set existing [get_bd_intf_nets -quiet -of_objects [get_bd_intf_pins -quiet $vidout/video_in]]
puts "current video_in net: '$existing'"

if {[llength [get_bd_cells -quiet sof_gen_0]] > 0} {
    delete_bd_objs [get_bd_cells sof_gen_0]
    puts "removed an earlier sof_gen_0"
}

# --- open the hop ------------------------------------------------------------------------
if {$existing ne ""} {
    if {[catch {delete_bd_objs $existing} cerr]} {
        puts "ERROR: could not remove the direct net: $cerr"
        current_bd_instance /
        exit 1
    }
    puts "removed '$existing'"
}

# --- create the kernel here --------------------------------------------------------------
create_bd_cell -type ip -vlnv xilinx.com:hls:sof_gen:1.0 sof_gen_0
set sof [get_bd_cells sof_gen_0]
puts "created /video/hdmi_out/sof_gen_0"

foreach p [get_bd_intf_pins -of_objects $sof] {
    puts "  interface [get_property NAME $p]"
}

set in_pin  [get_bd_intf_pins -quiet sof_gen_0/s_in]
set out_pin [get_bd_intf_pins -quiet sof_gen_0/s_out]
if {$in_pin eq "" || $out_pin eq ""} {
    puts "ERROR: expected s_in / s_out on the kernel"
    current_bd_instance /
    exit 1
}

# --- wire, only where still open ---------------------------------------------------------
set src [get_bd_intf_pins -quiet pixel_unpack/stream_out_24]
set dst [get_bd_intf_pins -quiet frontend/v_axi4s_vid_out_0/video_in]

foreach pair [list [list "in"  $src    $in_pin] [list "out" $out_pin $dst]] {
    lassign $pair label a b
    set na [get_bd_intf_nets -quiet -of_objects $a]
    set nb [get_bd_intf_nets -quiet -of_objects $b]
    if {$na ne "" && $na eq $nb} {
        puts "$label: already joined by '$na'"
        continue
    }
    # create_bd_cell can leave a half net on the upstream pin: the net exists but the new cell's pin
    # is not on it, so connect_bd_intf_net refuses with "already connected". Clearing both ends
    # first is what makes this deterministic.
    foreach stale [list $na $nb] {
        if {$stale ne ""} {
            catch {delete_bd_objs $stale}
            puts "$label: cleared '$stale'"
        }
    }
    if {[catch {connect_bd_intf_net $a $b} cerr]} {
        puts "$label: CONNECT FAILED $cerr"
    } else {
        puts "$label: connected"
    }
}

# --- clock and reset from the video core -------------------------------------------------
if {[catch {connect_bd_net [get_bd_pins frontend/v_axi4s_vid_out_0/aclk] \
                          [get_bd_pins sof_gen_0/ap_clk]} cerr]} { puts "clock: $cerr" } \
else { puts "clock connected" }

set rst_pin [get_bd_pins -quiet sof_gen_0/ap_rst_n]
set reset_net [get_bd_nets -quiet -of_objects [get_bd_pins frontend/v_axi4s_vid_out_0/aresetn]]
if {$rst_pin ne "" && $reset_net ne ""} {
    if {[catch {connect_bd_net $reset_net $rst_pin} cerr]} { puts "reset: $cerr" } \
    else { puts "reset connected" }
}

current_bd_instance /

catch {validate_bd_design}
save_bd_design
puts "design saved"

# --- verify ------------------------------------------------------------------------------
set ok 1
foreach path {/video/hdmi_out/sof_gen_0/s_in /video/hdmi_out/sof_gen_0/s_out} {
    set p [get_bd_intf_pins -quiet $path]
    set n [get_bd_intf_nets -quiet -of_objects $p]
    puts "  $path -> '$n'"
    if {$n eq ""} { set ok 0 }
}
if {!$ok} {
    puts "RESULT: SOF STREAM DANGLING"
    exit 1
}

reset_target all [get_files -quiet base.bd]
generate_target all [get_files -quiet base.bd] -force
puts "RESULT: SOF KERNEL INSERTED AS AN INTERFACE HOP"
exit 0
