# Restore the four AXI4-Stream interface connections and the video reset driver.
#
#   vivado -mode batch -source build\overlay_hdmi_enhance\restore_streams.tcl
#
# The stream path in this design is
#   VDMA -> stamp_in_0 -> enhance_cfg_0 -> stamp_out_0 -> pixel_unpack -> v_axi4s_vid_out
# and every hop is an AXI4-Stream *interface*. Repeated cell deletions during the SOF experiments
# removed those interface nets, and /video/aresetn lost its driver, which in turn makes further
# connect_bd_intf_net calls fail. Reset first, then the stream hops, then check_bd.tcl.

set script_dir [file dirname [file normalize [info script]]]
set proj_file  [file join $script_dir ".work" "tree" "boards" "Pynq-Z2" "base" "base" "base.xpr"]

open_project $proj_file
open_bd_design [get_files -quiet base.bd]

# --- 1) video reset ----------------------------------------------------------------------
set vid_rst [get_bd_pins -quiet /video/aresetn]
if {$vid_rst ne ""} {
    set net [get_bd_nets -quiet -of_objects $vid_rst]
    set driven 0
    if {$net ne ""} {
        foreach p [get_bd_pins -quiet -of_objects $net] {
            if {[get_property DIR $p] eq "O"} { set driven 1; break }
        }
    }
    if {!$driven} {
        # Take the driver from a sibling block inside the video hierarchy that is still driven.
        set driver ""
        foreach candidate [get_bd_pins -hierarchical -quiet \
                -filter {NAME =~ "*aresetn*" && DIR == "O"}] {
            set cnet [get_bd_nets -quiet -of_objects $candidate]
            if {$cnet eq ""} { continue }
            set members [get_bd_pins -quiet -of_objects $cnet]
            if {[llength $members] > 1} { set driver $candidate; break }
        }
        if {$driver eq ""} {
            set driver [get_bd_pins -quiet /rst_ps7_0_fclk1/peripheral_aresetn]
        }
        if {$driver ne ""} {
            if {[catch {connect_bd_net $driver $vid_rst} cerr]} {
                puts "video reset: $cerr"
            } else {
                puts "video reset driven from $driver"
            }
        } else {
            puts "WARNING: no candidate reset driver found"
        }
    } else {
        puts "video reset already driven"
    }
}

# --- 2) stream hops ----------------------------------------------------------------------
# Each entry: {label upstream-intf-pin downstream-intf-pin}
set hops [list \
    [list "vdma -> stamp_in"    /video/axi_vdma/M_AXIS_MM2S       /stamp_in_0/s_axis] \
    [list "stamp_in -> kernel"  /stamp_in_0/m_axis                /enhance_cfg_0/s_in] \
    [list "kernel -> stamp_out" /enhance_cfg_0/s_out              /stamp_out_0/s_axis] \
    [list "stamp_out -> unpack" /stamp_out_0/m_axis               /video/hdmi_out/pixel_unpack/stream_in_32] \
    [list "unpack -> vid_out"   /video/hdmi_out/pixel_unpack/stream_out_24 \
                                /video/hdmi_out/frontend/v_axi4s_vid_out_0/video_in] \
]

foreach hop $hops {
    lassign $hop label src_path dst_path
    set src [get_bd_intf_pins -quiet $src_path]
    set dst [get_bd_intf_pins -quiet $dst_path]
    if {$src eq "" || $dst eq ""} {
        puts "$label: pin missing (src='$src_path' dst='$dst_path')"
        continue
    }
    set existing [get_bd_intf_nets -quiet -of_objects $dst]
    if {$existing ne ""} {
        puts "$label: already connected ($existing)"
        continue
    }
    if {[catch {connect_bd_intf_net $src $dst} cerr]} {
        puts "$label: FAILED $cerr"
    } else {
        puts "$label: connected"
    }
}

catch {validate_bd_design}
save_bd_design
puts "design saved"

# --- 3) report ----------------------------------------------------------------------------
set missing {}
foreach path {/video/hdmi_out/frontend/v_axi4s_vid_out_0/video_in
               /enhance_cfg_0/s_in /enhance_cfg_0/s_out} {
    set p [get_bd_intf_pins -quiet $path]
    if {$p eq "" || [get_bd_intf_nets -quiet -of_objects $p] eq ""} {
        lappend missing $path
    }
}
if {[llength $missing] > 0} {
    puts "STILL MISSING: $missing"
    puts "RESULT: STREAMS INCOMPLETE"
    exit 1
}
puts "RESULT: STREAMS RESTORED"
exit 0
