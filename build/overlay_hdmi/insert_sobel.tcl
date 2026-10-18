# -----------------------------------------------------------------------------
# Insert the Sobel kernel into the PYNQ-Z2 base overlay block design.
#
# Run after base.tcl has created ./base/base.xpr (see build.bat).
#
# What it changes
#   The stock base overlay routes video through the VDMA frame buffer:
#       video/hdmi_in/out_stream -> axi_vdma -> DDR -> axi_vdma
#                                -> video/hdmi_out/in_stream
#   This script cuts both ends and wires the stream straight through the kernel:
#       video/hdmi_in/out_stream -> sobel_0 -> video/hdmi_out/in_stream
#   i.e. the low-latency "pipeline" path (about one line of latency instead of a
#   frame). The VDMA stays instantiated but unused, so nothing else in the PYNQ
#   video driver stops working.
#
# Why the kernel fits without glue logic
#   pixel_pack already produces one 32-bit AXI4-Stream beat per pixel (RGB in the
#   low 24 bits) and runs on clk_142M, which is exactly what sobel_stream is
#   built for (SOBEL_PIX_W=32) and what it closes timing at (est. 194 MHz).
#
# Args (tclargs): <project_dir> <sobel_ip_repo>
# -----------------------------------------------------------------------------
set project_dir [lindex $argv end-1]
set sobel_ip    [lindex $argv end]

if {$project_dir eq "" || $sobel_ip eq ""} {
    puts "usage: insert_sobel.tcl <project_dir> <sobel_ip_repo_dir>"
    exit 1
}
puts "project : $project_dir"
puts "sobel ip: $sobel_ip"

cd $project_dir
open_project {base/base.xpr}

# The kernel has to be visible before the block design is opened, otherwise the
# VLNV lookup inside create_bd_cell fails.
set repo_paths [get_property ip_repo_paths [current_project]]
if {[lsearch -exact $repo_paths $sobel_ip] < 0} {
    lappend repo_paths $sobel_ip
}
set_property ip_repo_paths $repo_paths [current_project]
update_ip_catalog

open_bd_design {base/base.srcs/sources_1/bd/base/base.bd}

# --- cut the two ends of the VDMA loopback ---------------------------------
set in_port  [get_bd_intf_pins video/hdmi_in/out_stream]
set out_port [get_bd_intf_pins video/hdmi_out/in_stream]
if {[llength $in_port] == 0 || [llength $out_port] == 0} {
    puts "ERROR: video stream ports not found"
    exit 1
}
foreach pin [list $in_port $out_port] {
    foreach net [get_bd_intf_nets -of_objects $pin] {
        puts "deleting net [get_property NAME $net]"
        delete_bd_objs $net
    }
}

# --- add the kernel and wire it --------------------------------------------
set sobel [create_bd_cell -type ip -vlnv xilinx.com:hls:sobel_stream:1.0 sobel_0]
connect_bd_intf_net [get_bd_intf_pins video/hdmi_in/out_stream]  [get_bd_intf_pins sobel_0/s_in]
connect_bd_intf_net [get_bd_intf_pins sobel_0/s_out]              [get_bd_intf_pins video/hdmi_out/in_stream]

# Reuse the clock/reset nets that already feed the video hierarchy, instead of
# guessing at top-level pin names.
foreach {src dst} [list video/clk_142M sobel_0/ap_clk \
                        video/periph_resetn_clk142M sobel_0/ap_rst_n] {
    set nets [get_bd_nets -quiet -of_objects [get_bd_pins $src]]
    if {[llength $nets] == 0} {
        puts "ERROR: no net on $src, cannot clock the kernel"
        exit 1
    }
    set net_name [get_property NAME [lindex $nets 0]]
    puts "connect $dst to net $net_name"
    connect_bd_net -net $net_name [get_bd_pins $dst]
}

validate_bd_design
save_bd_design

puts "RESULT: INSERT OK"
exit 0
