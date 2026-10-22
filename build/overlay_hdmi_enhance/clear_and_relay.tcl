# Clear pin-level stream overrides, then re-lay every stream hop as an interface.
#
#   vivado -mode batch -source build\overlay_hdmi_enhance\clear_and_relay.tcl
#
# The pin-by-pin wiring of the abandoned RTL SOF attempt left "overridden by the user" markers on
# the stream pins (BD 41-1271). While those exist, connect_bd_intf_net refuses to lay an interface
# net, so the design keeps looking broken even after the cells themselves are gone.
#
# Order: delete the nets on every stream pin of the five blocks in the chain, then connect the hops
# as interfaces, then check the result.

set script_dir [file dirname [file normalize [info script]]]
set proj_file  [file join $script_dir ".work" "tree" "boards" "Pynq-Z2" "base" "base" "base.xpr"]

open_project $proj_file
open_bd_design [get_files -quiet base.bd]

set blocks [list /video/axi_vdma /stamp_in_0 /enhance_cfg_0 /stamp_out_0 \
                 /video/hdmi_out/pixel_unpack \
                 /video/hdmi_out/frontend/v_axi4s_vid_out_0]

set suffixes {TDATA TVALID TREADY TLAST TUSER TKEEP TSTRB TID TDEST}
set cleared 0
foreach block $blocks {
    set cell [get_bd_cells -quiet $block]
    if {$cell eq ""} { continue }
    foreach pin [get_bd_pins -quiet -of_objects $cell] {
        set name [get_property NAME $pin]
        set hit 0
        foreach suffix $suffixes {
            if {[string match "*$suffix" [string toupper $name]]} { set hit 1; break }
        }
        if {!$hit} { continue }
        set net [get_bd_nets -quiet -of_objects $pin]
        if {$net ne ""} {
            catch {delete_bd_objs $net}
            incr cleared
        }
    }
}
puts "cleared $cleared stream pin nets"

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
        puts "$label: MISSING PIN (src='$src_path' dst='$dst_path')"
        continue
    }
    if {[catch {connect_bd_intf_net $src $dst} cerr]} {
        puts "$label: FAILED $cerr"
    } else {
        puts "$label: connected"
    }
}

# Video reset must have a source or validate fails and further connects are refused.
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
        set driver [get_bd_pins -quiet /rst_ps7_0_fclk1/peripheral_aresetn]
        if {$driver eq ""} {
            foreach candidate [get_bd_pins -hierarchical -quiet \
                    -filter {NAME =~ "*peripheral_aresetn*"}] {
                set cnet [get_bd_nets -quiet -of_objects $candidate]
                if {$cnet ne "" && [llength [get_bd_pins -quiet -of_objects $cnet]] > 1} {
                    set driver $candidate
                    break
                }
            }
        }
        if {$driver ne ""} {
            if {[catch {connect_bd_net $driver $vid_rst} cerr]} {
                puts "video reset: $cerr"
            } else {
                puts "video reset driven from $driver"
            }
        }
    }
}

catch {validate_bd_design}
save_bd_design
puts "design saved"

set missing {}
foreach path {/video/hdmi_out/frontend/v_axi4s_vid_out_0/video_in
               /enhance_cfg_0/s_in /enhance_cfg_0/s_out} {
    set p [get_bd_intf_pins -quiet $path]
    if {$p eq "" || [get_bd_intf_nets -quiet -of_objects $p] eq ""} { lappend missing $path }
}
if {[llength $missing] > 0} {
    puts "STILL MISSING: $missing"
    puts "RESULT: STREAMS INCOMPLETE"
    exit 1
}
puts "RESULT: STREAMS RELAID AS INTERFACES"
exit 0
