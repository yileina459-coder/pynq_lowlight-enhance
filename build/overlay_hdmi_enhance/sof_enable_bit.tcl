# Rebuild the SOF generator cell and restore every net it used to carry.
#
#   vivado -mode batch -source build\overlay_hdmi_enhance\sof_enable_bit.tcl
#
# Two lessons from the failed attempts are baked in:
#   * deleting the cell also deletes the nets it participated in, including the vid_out's reset net
#     (it only had two pins), so the reset driver has to be recorded *before* the delete;
#   * a half-finished run can leave the cell absent while the design is saved, which silently cuts
#     pixel_unpack from v_axi4s_vid_out - the stream stops and the VDMA hangs on the board.
#
# The generator gets a runtime enable on gpio_enh_cfg[30] so SOF-on and SOF-off can be compared
# with a register write instead of a 35-minute rebuild.

set script_dir [file dirname [file normalize [info script]]]
set proj_file  [file join $script_dir ".work" "tree" "boards" "Pynq-Z2" "base" "base" "base.xpr"]

open_project $proj_file
open_bd_design [get_files -quiet base.bd]

set gpio [get_bd_cells -quiet /gpio_enh_cfg]
if {$gpio eq ""} { puts "ERROR: missing /gpio_enh_cfg"; exit 1 }

set unpack [get_bd_cells /video/hdmi_out/pixel_unpack]
set vidout [get_bd_cells /video/hdmi_out/frontend/v_axi4s_vid_out_0]

# --- record the reset driver before anything is deleted --------------------------------
set vid_reset_pin [get_bd_pins -quiet $vidout/aresetn]
set reset_net [get_bd_nets -quiet -of_objects $vid_reset_pin]
set reset_drv ""
if {$reset_net ne ""} {
    # The driving end can be a hierarchy port rather than a plain output pin (this net is
    # /video/hdmi_out/frontend/aresetn_1, an internal hierarchy net), so take the first pin on the
    # net that is not the vid_out reset pin itself.
    foreach candidate [get_bd_pins -quiet -of_objects $reset_net] {
        if {$candidate ne $vid_reset_pin} { set reset_drv $candidate; break }
    }
}
if {$reset_drv eq ""} {
    puts "ERROR: could not identify the reset driver (net: $reset_net)"
    exit 1
}
puts "reset driver recorded: $reset_drv"

# --- rebuild the generator -------------------------------------------------------------
set sof [get_bd_cells -quiet /sof_gen_0]
if {$sof ne ""} {
    delete_bd_objs [get_bd_cells $sof]
    puts "deleted the old /sof_gen_0"
}
create_bd_cell -type module -reference axis_sof_gen /sof_gen_0
set sof [get_bd_cells /sof_gen_0]
puts "created /sof_gen_0"

# --- stream wiring ---------------------------------------------------------------------
if {[catch {
    connect_bd_net [get_bd_pins $unpack/stream_out_24_TDATA]  [get_bd_pins $sof/s_tdata]
    connect_bd_net [get_bd_pins $unpack/stream_out_24_TVALID] [get_bd_pins $sof/s_tvalid]
    connect_bd_net [get_bd_pins $unpack/stream_out_24_TLAST]  [get_bd_pins $sof/s_tlast]
    connect_bd_net [get_bd_pins $unpack/stream_out_24_TUSER]  [get_bd_pins $sof/s_tuser]
    connect_bd_net [get_bd_pins $sof/s_tready]                [get_bd_pins $unpack/stream_out_24_TREADY]
} cerr]} { puts "CONNECT FAILED (slave side): $cerr" }

if {[catch {
    connect_bd_net [get_bd_pins $sof/m_tdata]  [get_bd_pins $vidout/s_axis_video_tdata]
    connect_bd_net [get_bd_pins $sof/m_tvalid] [get_bd_pins $vidout/s_axis_video_tvalid]
    connect_bd_net [get_bd_pins $sof/m_tlast]  [get_bd_pins $vidout/s_axis_video_tlast]
    connect_bd_net [get_bd_pins $vidout/s_axis_video_tready] [get_bd_pins $sof/m_tready]
    connect_bd_net [get_bd_pins $sof/m_tuser]  [get_bd_pins $vidout/s_axis_video_tuser]
} cerr]} { puts "CONNECT FAILED (master side): $cerr" }

if {[catch {connect_bd_net [get_bd_pins $vidout/aclk] [get_bd_pins $sof/aclk]} cerr]} {
    puts "CONNECT FAILED (aclk): $cerr"
}

# --- reset: reattach both the generator and the vid_out --------------------------------
foreach sink {/sof_gen_0/aresetn /video/hdmi_out/frontend/v_axi4s_vid_out_0/aresetn} {
    set p [get_bd_pins -quiet $sink]
    if {$p eq ""} { continue }
    set existing [get_bd_nets -quiet -of_objects $p]
    if {$existing ne "" && $existing ne $reset_net} { catch {delete_bd_objs $existing} }
    if {[catch {connect_bd_net $reset_drv $p} cerr]} {
        puts "RESET CONNECT FAILED at $sink :: $cerr"
    } else {
        puts "reset: $reset_drv -> $sink"
    }
}

# --- runtime enable ---------------------------------------------------------------------
if {[llength [get_bd_cells -quiet /sof_en_slice]] == 0} {
    create_bd_cell -type ip -vlnv xilinx.com:ip:xlslice /sof_en_slice
    puts "created /sof_en_slice"
}
set sl [get_bd_cells /sof_en_slice]
set_property -dict [list CONFIG.DIN_WIDTH {32} CONFIG.DIN_FROM {30} CONFIG.DIN_TO {30}] $sl
if {[catch {
    connect_bd_net [get_bd_pins $gpio/gpio2_io_o] [get_bd_pins $sl/Din]
    connect_bd_net [get_bd_pins $sl/Dout] [get_bd_pins $sof/sof_enable]
} cerr]} { puts "CONNECT FAILED (enable slice): $cerr" }
puts "enable: gpio_enh_cfg[30] -> sof_enable"

validate_bd_design
save_bd_design

set dangling {}
foreach p [get_bd_pins -of_objects $sof] {
    if {[get_property DIR $p] ne "I"} { continue }
    if {[get_bd_nets -quiet -of_objects $p] eq ""} { lappend dangling [get_property NAME $p] }
}
if {[llength $dangling] > 0} {
    puts "STILL DANGLING: $dangling"
    exit 1
}
puts "check: every input of /sof_gen_0 is driven"

foreach pin {/video/hdmi_out/pixel_unpack/stream_out_24_TDATA
             /video/hdmi_out/frontend/v_axi4s_vid_out_0/s_axis_video_tdata} {
    if {[get_bd_nets -quiet -of_objects [get_bd_pins -quiet $pin]] eq ""} {
        puts "STREAM BROKEN at $pin"
        exit 1
    }
}
puts "check: pixel_unpack -> v_axi4s_vid_out stream is connected"

reset_target all [get_files -quiet base.bd]
generate_target all [get_files -quiet base.bd] -force
puts "RESULT: SOF CELL REBUILT WITH RUNTIME ENABLE"
exit 0
