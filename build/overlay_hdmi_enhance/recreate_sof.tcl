# Recreate the SOF generator cell so the packaged copy matches the edited RTL.
#
#   vivado -mode batch -source build\overlay_hdmi_enhance\recreate_sof.tcl
#
# A module reference is packaged into an XCI and a synthesised DCP is cached under .gen, so
# editing axis_sof_gen.v alone changes nothing - the same trap that hid the cfg_bram changes for
# three rebuilds earlier. Deleting the cell and its package, then recreating it, is what picks up
# new RTL.

set script_dir [file dirname [file normalize [info script]]]
set repo_root  [file normalize [file join $script_dir ".." ".."]]
set proj_file  [file join $script_dir ".work" "tree" "boards" "Pynq-Z2" "base" "base" "base.xpr"]
set proj_root  [file join $script_dir ".work" "tree" "boards" "Pynq-Z2" "base" "base"]

open_project $proj_file
open_bd_design [get_files -quiet base.bd]

# --- remove the old cell and its package -------------------------------------------------
if {[llength [get_bd_cells -quiet /sof_gen_0]] > 0} {
    delete_bd_objs [get_bd_cells /sof_gen_0]
    puts "deleted /sof_gen_0"
}
save_bd_design
close_bd_design [current_bd_design]

foreach stale [list \
        [file join $proj_root "base.srcs" "sources_1" "bd" "base" "ip" "base_sof_gen_0_0"] \
        [file join $proj_root "base.gen" "sources_1" "bd" "base" "ip" "base_sof_gen_0_0"]] {
    if {[file exists $stale]} {
        file delete -force $stale
        puts "removed [file tail $stale]"
    }
}

# --- recreate from the current source ----------------------------------------------------
open_bd_design [get_files -quiet base.bd]
create_bd_cell -type module -reference axis_sof_gen /sof_gen_0

set sof    [get_bd_cells /sof_gen_0]
set unpack [get_bd_cells /video/hdmi_out/pixel_unpack]
set vidout [get_bd_cells /video/hdmi_out/frontend/v_axi4s_vid_out_0]

foreach suffix {TDATA TVALID TREADY TLAST} {
    foreach pin [list $unpack/stream_out_24_$suffix $vidout/s_axis_video_$suffix] {
        set p [get_bd_pins -quiet $pin]
        if {$p eq ""} { continue }
        set net [get_bd_nets -quiet -of_objects $p]
        if {$net ne ""} { catch {delete_bd_objs $net} }
    }
}

connect_bd_net [get_bd_pins $unpack/stream_out_24_TDATA]  [get_bd_pins $sof/s_tdata]
connect_bd_net [get_bd_pins $unpack/stream_out_24_TVALID] [get_bd_pins $sof/s_tvalid]
connect_bd_net [get_bd_pins $unpack/stream_out_24_TLAST]  [get_bd_pins $sof/s_tlast]
connect_bd_net [get_bd_pins $sof/s_tready]                 [get_bd_pins $unpack/stream_out_24_TREADY]
connect_bd_net [get_bd_pins $unpack/stream_out_24_TUSER]  [get_bd_pins $sof/s_tuser]

connect_bd_net [get_bd_pins $sof/m_tdata]  [get_bd_pins $vidout/s_axis_video_tdata]
connect_bd_net [get_bd_pins $sof/m_tvalid] [get_bd_pins $vidout/s_axis_video_tvalid]
connect_bd_net [get_bd_pins $sof/m_tlast]  [get_bd_pins $vidout/s_axis_video_tlast]
connect_bd_net [get_bd_pins $vidout/s_axis_video_tready] [get_bd_pins $sof/m_tready]
connect_bd_net [get_bd_pins $sof/m_tuser]  [get_bd_pins $vidout/s_axis_video_tuser]

connect_bd_net [get_bd_pins $vidout/aclk] [get_bd_pins $sof/aclk]
set reset_net [get_bd_nets -quiet -of_objects [get_bd_pins $vidout/aresetn]]
if {$reset_net eq ""} {
    puts "ERROR: vid_out reset has no net"
    exit 1
}
connect_bd_net $reset_net [get_bd_pins $sof/aresetn]
puts "wired /sof_gen_0 (clock and reset from vid_out)"

validate_bd_design
save_bd_design

set dangling {}
foreach p [get_bd_pins -of_objects $sof] {
    if {[get_property DIR $p] ne "I"} { continue }
    if {[get_bd_nets -quiet -of_objects $p] eq ""} {
        lappend dangling [get_property NAME $p]
    }
}
if {[llength $dangling] > 0} {
    puts "STILL DANGLING: $dangling"
    exit 1
}
puts "check: every input of /sof_gen_0 is driven"

reset_target all [get_files -quiet base.bd]
generate_target all [get_files -quiet base.bd] -force
puts "RESULT: SOF CELL RECREATED"
exit 0
