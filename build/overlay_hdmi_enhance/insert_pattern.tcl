# -----------------------------------------------------------------------------
# Swap the HDMI IN source for the internal pattern generator.
#
# Run on the project that already has the enhance kernel and the two GPIOs
# (build/overlay_hdmi_enhance/.work/.../base.xpr), so only implementation has to
# be redone afterwards - the ~200 out-of-context IP runs are already cached.
#
# What it changes
#   ... video/hdmi_in/out_stream -> stamp_in_0/s_axis ...
# becomes
#   video_pattern_gen_0/m_axis  -> stamp_in_0/s_axis
#
# The rest of the pipeline (stamps, enhance, config GPIO, latency GPIO) is
# untouched, so the latency readout and the presets keep working exactly as on the
# external-input build.
#
# Args (tclargs): <base_dir> <rtl_root>
# -----------------------------------------------------------------------------
set base_dir [lindex $argv end-1]
set rtl_root [lindex $argv end]

if {$base_dir eq "" || $rtl_root eq ""} {
    puts "usage: insert_pattern.tcl <base_dir> <rtl_root>"
    exit 1
}
puts "base_dir: $base_dir"
puts "rtl_root: $rtl_root"

set rtl [file join $rtl_root "video_pattern_gen" "video_pattern_gen.v"]
if {![file exists $rtl]} {
    puts "ERROR: missing $rtl"
    exit 1
}

cd $base_dir
open_project {base/base.xpr}
if {[llength [get_files -quiet $rtl]] == 0} {
    add_files -norecurse $rtl
}
update_compile_order -fileset sources_1

open_bd_design {base/base.srcs/sources_1/bd/base/base.bd}

set stamp_in [get_bd_pins axis_cycle_stamp_0/s_axis_TVALID]

# --- cut the external-input stream feeding stamp_in --------------------------
# Delete from the consumer side: whatever net feeds stamp_in/s_axis is the
# external video stream, no matter what it is called. Deleting from the
# video/hdmi_in/out_stream side was unreliable - that port is inside a hierarchy
# and the first attempt left the net ("video_out_stream1") in place, so the
# reconnect failed with BD 41-396.
set stamp_cells_pre [get_bd_cells -quiet -filter {NAME =~ "*stamp_in*"}]
if {[llength $stamp_cells_pre] == 0} {
    puts "ERROR: stamp_in cell not found"
    exit 1
}
set stamp_pre [lindex $stamp_cells_pre 0]
foreach net [get_bd_intf_nets -quiet -of_objects [get_bd_intf_pins ${stamp_pre}/s_axis]] {
    puts "deleting net [get_property NAME $net]"
    delete_bd_objs $net
}

# --- insert the generator ----------------------------------------------------
set gen [create_bd_cell -type module -reference video_pattern_gen vpg_0]
set_property -dict [list CONFIG.H_ACTIVE {1280} CONFIG.V_ACTIVE {720}] $gen

set stamp_cells [get_bd_cells -quiet -filter {NAME =~ "*stamp_in*"}]
if {[llength $stamp_cells] == 0} {
    puts "ERROR: stamp_in cell not found; this script expects the enhance overlay"
    exit 1
}
set stamp_cell [lindex $stamp_cells 0]
puts "connecting vpg_0 -> $stamp_cell"

# stamp_in already drives enhance, so only its input needs a new producer
connect_bd_intf_net [get_bd_intf_pins vpg_0/m_axis] [get_bd_intf_pins ${stamp_cell}/s_axis]

# --- clock/reset: same pixel-clock domain as the kernel ----------------------
set aclk_net  [get_property NAME [lindex [get_bd_nets -quiet -of_objects [get_bd_pins ${stamp_cell}/aclk]] 0]]
set arstn_net [get_property NAME [lindex [get_bd_nets -quiet -of_objects [get_bd_pins ${stamp_cell}/aresetn]] 0]]
puts "clock net: $aclk_net / reset net: $arstn_net"
connect_bd_net -net $aclk_net  [get_bd_pins vpg_0/aclk]
connect_bd_net -net $arstn_net [get_bd_pins vpg_0/aresetn]

assign_bd_address
validate_bd_design
save_bd_design

puts "RESULT: PATTERN INSERT OK"
exit 0
