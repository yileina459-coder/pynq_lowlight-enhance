# Insert the HLS SOF generator using AXI4-Stream *interface* connections.
#
#   vivado -mode batch -source build\overlay_hdmi_enhance\add_sof_hls.tcl
#
# The RTL version was wired pin by pin, which broke the interface bridge between pixel_unpack and
# v_axi4s_vid_out: the .hwh then described the output core's input as an interface port that no
# longer had a matching signal, and PYNQ refused to load the overlay with
# MetadataObjectNotFound: s_axis_video_tdata[...]. An HLS kernel exposes s_in/s_out as interfaces,
# so the design stays interface-to-interface.

set script_dir [file dirname [file normalize [info script]]]
set repo_root  [file normalize [file join $script_dir ".." ".."]]
set proj_file  [file join $script_dir ".work" "tree" "boards" "Pynq-Z2" "base" "base" "base.xpr"]
set proj_root  [file join $script_dir ".work" "tree" "boards" "Pynq-Z2" "base" "base"]

open_project $proj_file

# --- make the IP visible to the project -------------------------------------------------
set ip_repo [file join $script_dir ".work" "sof_ip"]
if {![file exists [file join $ip_repo "component.xml"]]} {
    puts "ERROR: $ip_repo does not contain an extracted IP (component.xml missing)"
    puts "       extract build/hls/sof_gen/export/sof_gen.zip there first"
    exit 1
}
set existing [get_property IP_REPO_PATHS [current_project]]
if {[lsearch -exact $existing $ip_repo] < 0} {
    set_property IP_REPO_PATHS [concat $existing $ip_repo] [current_project]
}
update_ip_catalog -rebuild
puts "ip catalog rebuilt from $ip_repo"

open_bd_design [get_files -quiet base.bd]

# --- remove the old RTL-based attempt ---------------------------------------------------
foreach cell {/sof_gen_0 /sof_en_slice} {
    set c [get_bd_cells -quiet $cell]
    if {$c ne ""} {
        delete_bd_objs [get_bd_cells $c]
        puts "deleted $cell"
    }
}
save_bd_design
close_bd_design [current_bd_design]

# The packaged module reference of the RTL version is stale; drop it so nothing picks it up.
foreach stale [list \
        [file join $proj_root "base.srcs" "sources_1" "bd" "base" "ip" "base_sof_gen_0_0"] \
        [file join $proj_root "base.gen" "sources_1" "bd" "base" "ip" "base_sof_gen_0_0"] \
        [file join $proj_root "base.gen" "sources_1" "bd" "mref" "axis_sof_gen"]] {
    if {[file exists $stale]} {
        file delete -force $stale
        puts "removed [file tail $stale]"
    }
}

# --- create the HLS kernel and wire interfaces ------------------------------------------
open_bd_design [get_files -quiet base.bd]
create_bd_cell -type ip -vlnv xilinx.com:hls:sof_gen:1.0 /sof_gen_0
set sof [get_bd_cells /sof_gen_0]
puts "created /sof_gen_0 from the HLS IP"

set unpack [get_bd_cells /video/hdmi_out/pixel_unpack]
set vidout [get_bd_cells /video/hdmi_out/frontend/v_axi4s_vid_out_0]

set in_intf  [get_bd_intf_pins -quiet $unpack/stream_out_24]
set out_intf [get_bd_intf_pins -quiet $vidout/video_in]
if {$in_intf eq "" || $out_intf eq ""} {
    puts "ERROR: could not find the stream interfaces"
    puts "  pixel_unpack interfaces:"
    foreach p [get_bd_intf_pins -of_objects $unpack] { puts "    [get_property NAME $p]" }
    puts "  vid_out interfaces:"
    foreach p [get_bd_intf_pins -of_objects $vidout] { puts "    [get_property NAME $p]" }
    exit 1
}

connect_bd_intf_net $in_intf  [get_bd_intf_pins $sof/s_in]
connect_bd_intf_net [get_bd_intf_pins $sof/s_out] $out_intf
puts "connected pixel_unpack -> sof_gen -> v_axi4s_vid_out as interfaces"

# --- clock and reset -------------------------------------------------------------------
if {[catch {connect_bd_net [get_bd_pins $vidout/aclk] [get_bd_pins $sof/ap_clk]} cerr]} {
    puts "CLOCK CONNECT FAILED: $cerr"
}
set rst [get_bd_pins -quiet $sof/ap_rst_n]
if {$rst ne ""} {
    set reset_net [get_bd_nets -quiet -of_objects [get_bd_pins $vidout/aresetn]]
    if {$reset_net ne ""} {
        if {[catch {connect_bd_net $reset_net $rst} cerr]} {
            puts "RESET CONNECT FAILED: $cerr"
        } else {
            puts "reset: $reset_net -> /sof_gen_0/ap_rst_n"
        }
    }
}

validate_bd_design
save_bd_design

# --- the stream must be an interface end to end -----------------------------------------
set in_net  [get_bd_intf_nets -quiet -of_objects [get_bd_intf_pins $sof/s_in]]
set out_net [get_bd_intf_nets -quiet -of_objects [get_bd_intf_pins $sof/s_out]]
if {$in_net eq "" || $out_net eq ""} {
    puts "STREAM NOT CONNECTED AS AN INTERFACE (in: $in_net, out: $out_net)"
    exit 1
}
puts "check: both stream sides are interface connections"

reset_target all [get_files -quiet base.bd]
generate_target all [get_files -quiet base.bd] -force
puts "RESULT: HLS SOF GENERATOR INSERTED"
exit 0
