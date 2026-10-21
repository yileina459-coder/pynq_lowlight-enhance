# Feed the kernel from the VDMA's MM2S channel (640x480 only demo path).
#
# Structure discovered by probing the block design:
#     /video/axi_vdma                the frame DMA lives *inside* the video hierarchy
#     net Conn3: /video/hdmi_in/out_stream <-> /video/out_stream1   (input -> S2MM)
#     net Conn4: /video/hdmi_out/in_stream <-> /video/in_stream1    (MM2S -> output)
#
# Our kernel insertion deleted Conn4 and drove hdmi_out/in_stream from stamp_out, which
# is why hdmi_out.writeframe() blocks in this overlay: the MM2S stream has no consumer
# any more. Connecting MM2S to stamp_in gives the PS a way to push frames through the
# kernel and out of the HDMI port at the only mode this board can drive (640x480).

set base_dir [lindex $argv end]
if {$base_dir eq ""} { puts "usage: source_from_vdma.tcl <base_dir>"; exit 1 }

cd $base_dir
open_project {base/base.xpr}
open_bd_design {base/base.srcs/sources_1/bd/base/base.bd}

set mm2s [get_bd_intf_pins -quiet /video/axi_vdma/M_AXIS_MM2S]
if {[llength $mm2s] == 0} {
    puts "M_AXIS_MM2S not found; listing the VDMA's interface pins:"
    foreach p [get_bd_intf_pins -quiet /video/axi_vdma/*] { puts "  $p" }
    exit 1
}
puts "MM2S pin: $mm2s"

# Remove whatever currently drives the kernel input.
foreach net [get_bd_intf_nets -quiet -of_objects [get_bd_intf_pins stamp_in_0/s_axis]] {
    puts "removing [get_property NAME $net] from stamp_in_0/s_axis"
    delete_bd_objs $net
}
# And drop the now-unused HDMI-input stream net.
foreach net [get_bd_intf_nets -quiet -of_objects [get_bd_intf_pins video/hdmi_in/out_stream]] {
    puts "removing [get_property NAME $net] from video/hdmi_in/out_stream"
    delete_bd_objs $net
}

if {[catch {connect_bd_intf_net $mm2s [get_bd_intf_pins stamp_in_0/s_axis]} err]} {
    puts "direct connect failed: $err"
    puts "trying via the hierarchy port instead"
    set port [get_bd_intf_pins -quiet /video/in_stream1]
    puts "  /video/in_stream1 = $port"
    if {[llength $port] > 0} {
        connect_bd_intf_net $port [get_bd_intf_pins stamp_in_0/s_axis]
        puts "  connected /video/in_stream1 -> stamp_in_0/s_axis"
    } else {
        exit 1
    }
} else {
    puts "connected MM2S -> stamp_in_0/s_axis"
}

validate_bd_design
save_bd_design
puts "RESULT: VDMA FEEDS THE KERNEL"
exit 0
