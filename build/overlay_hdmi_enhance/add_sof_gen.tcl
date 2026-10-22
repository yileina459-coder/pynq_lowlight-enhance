# Insert the SOF generator between pixel_unpack and v_axi4s_vid_out.
#
#   vivado -mode batch -source build\overlay_hdmi_enhance\add_sof_gen.tcl
#
# Why: v_axi4s_vid_out aligns frames to its timing generator on SOF (TUSER). The VDMA holds TUSER
# low, so the core free-runs and the picture lands at an arbitrary pixel phase - the measured
# horizontal offset was 0 px in one session, 45 px in another and 89 px in a third, with the same
# bitstream. axis_sof_gen manufactures the missing SOF from TLAST + a line counter.
#
# The module is new, so its module reference is created fresh: a new name cannot hit the cached
# package/DCP problem that the earlier attempts ran into.

set script_dir [file dirname [file normalize [info script]]]
set repo_root  [file normalize [file join $script_dir ".." ".."]]
set proj_file  [file join $script_dir ".work" "tree" "boards" "Pynq-Z2" "base" "base" "base.xpr"]

open_project $proj_file
open_bd_design [get_files -quiet base.bd]

set rtl [file join $repo_root "src" "rtl" "axis_sof_gen" "axis_sof_gen.v"]
if {[llength [get_files -quiet $rtl]] == 0} {
    add_files -norecurse -fileset sources_1 $rtl
    puts "added $rtl"
}
update_compile_order -fileset sources_1

set unpack [get_bd_cells -quiet /video/hdmi_out/pixel_unpack]
set vidout [get_bd_cells -quiet /video/hdmi_out/frontend/v_axi4s_vid_out_0]
if {$unpack eq "" || $vidout eq ""} {
    puts "ERROR: could not find pixel_unpack or v_axi4s_vid_out"
    exit 1
}

# Create the cell first so its pins exist.
if {[llength [get_bd_cells -quiet /sof_gen_0]] == 0} {
    create_bd_cell -type module -reference axis_sof_gen /sof_gen_0
    puts "created /sof_gen_0"
}

set sof [get_bd_cells /sof_gen_0]

# Wire it in. The existing nets are deleted first; connect_bd_net would otherwise refuse with
# "sink is already connected to another source".
set suffixes {TDATA TVALID TREADY TLAST TUSER}
foreach suffix $suffixes {
    set src [get_bd_pins -quiet $unpack/stream_out_24_$suffix]
    set old_net [get_bd_nets -quiet -of_objects $src]
    if {$old_net ne ""} {
        catch {delete_bd_objs $old_net}
    }
}
foreach suffix {TDATA TVALID TREADY} {
    set dst [get_bd_pins -quiet $vidout/s_axis_video_$suffix]
    set old_net [get_bd_nets -quiet -of_objects $dst]
    if {$old_net ne ""} {
        catch {delete_bd_objs $old_net}
    }
}

connect_bd_net [get_bd_pins $unpack/stream_out_24_TDATA]  [get_bd_pins $sof/s_tdata]
connect_bd_net [get_bd_pins $unpack/stream_out_24_TVALID] [get_bd_pins $sof/s_tvalid]
connect_bd_net [get_bd_pins $unpack/stream_out_24_TLAST]  [get_bd_pins $sof/s_tlast]
connect_bd_net [get_bd_pins $sof/s_tready]                 [get_bd_pins $unpack/stream_out_24_TREADY]

connect_bd_net [get_bd_pins $sof/m_tdata]  [get_bd_pins $vidout/s_axis_video_tdata]
connect_bd_net [get_bd_pins $sof/m_tvalid] [get_bd_pins $vidout/s_axis_video_tvalid]
connect_bd_net [get_bd_pins $sof/m_tlast]  [get_bd_pins $vidout/s_axis_video_tlast]
connect_bd_net [get_bd_pins $vidout/s_axis_video_tready] [get_bd_pins $sof/m_tready]
connect_bd_net [get_bd_pins $sof/m_tuser]  [get_bd_pins $vidout/s_axis_video_tuser]

# Clock and reset come from the video domain.
connect_bd_net [get_bd_pins $vidout/aclk] [get_bd_pins $sof/aclk]
set aresetn [get_bd_pins -quiet $vidout/aresetn]
if {$aresetn ne ""} {
    connect_bd_net $aresetn [get_bd_pins $sof/aresetn]
} else {
    set rst [get_bd_pins -quiet /rst_ps7_0_fclk1/peripheral_aresetn]
    if {$rst ne ""} {
        connect_bd_net $rst [get_bd_pins $sof/aresetn]
    }
}

puts "--- sof_gen pins after wiring ---"
foreach p [get_bd_pins -of_objects $sof] {
    puts "  [get_property NAME $p] -> [get_bd_nets -quiet -of_objects $p]"
}

validate_bd_design
save_bd_design
reset_target all [get_files -quiet base.bd]
generate_target all [get_files -quiet base.bd] -force
puts "RESULT: SOF GENERATOR INSERTED"
exit 0
