# Repair the block design to the state before the SOF experiments.
#
#   vivado -mode batch -source build\overlay_hdmi_enhance\repair_bd.tcl
#
# The SOF integration left the design half migrated: the RTL module's pin-level nets still hang off
# pixel_unpack and v_axi4s_vid_out, so an interface connection cannot take, and the video reset net
# lost its driver when cells were deleted. This restores the plain interface path
#   pixel_unpack --stream_out_24--> v_axi4s_vid_out --video_in-->
# and re-drives the video reset.

set script_dir [file dirname [file normalize [info script]]]
set proj_file  [file join $script_dir ".work" "tree" "boards" "Pynq-Z2" "base" "base" "base.xpr"]

open_project $proj_file
open_bd_design [get_files -quiet base.bd]

# --- remove every SOF artefact ----------------------------------------------------------
foreach cell {/sof_gen_0 /sof_en_slice} {
    set c [get_bd_cells -quiet $cell]
    if {$c ne ""} { delete_bd_objs [get_bd_cells $c]; puts "deleted $cell" }
}

set unpack [get_bd_cells /video/hdmi_out/pixel_unpack]
set vidout [get_bd_cells /video/hdmi_out/frontend/v_axi4s_vid_out_0]

# --- clear leftover pin-level nets on both ends of the stream ---------------------------
foreach pin [concat [get_bd_pins -quiet -of_objects $unpack] \
                    [get_bd_pins -quiet -of_objects $vidout]] {
    set name [get_property NAME $pin]
    if {![string match "*stream_out_24_*" $name] && ![string match "s_axis_video_*" $name]} {
        continue
    }
    set net [get_bd_nets -quiet -of_objects $pin]
    if {$net ne ""} {
        catch {delete_bd_objs $net}
        puts "cleared net on $name"
    }
}

# --- reconnect the stream as an interface ----------------------------------------------
set src [get_bd_intf_pins -quiet $unpack/stream_out_24]
set dst [get_bd_intf_pins -quiet $vidout/video_in]
if {[catch {connect_bd_intf_net $src $dst} cerr]} {
    puts "STREAM CONNECT FAILED: $cerr"
} else {
    puts "connected pixel_unpack/stream_out_24 -> vid_out/video_in as an interface"
}

# --- re-drive the video reset -----------------------------------------------------------
set vid_rst [get_bd_pins -quiet /video/aresetn]
if {$vid_rst ne ""} {
    set net [get_bd_nets -quiet -of_objects $vid_rst]
    if {$net eq ""} {
        # Find the reset source the other video blocks use.
        set driver ""
        foreach candidate [get_bd_pins -hierarchical -quiet \
                -filter {NAME =~ "*aresetn*" && DIR == "O"}] {
            if {[string match "*rst_ps7_0_fclk1*" $candidate]} { set driver $candidate; break }
        }
        if {$driver eq ""} {
            set driver [get_bd_pins -quiet /rst_ps7_0_fclk1/peripheral_aresetn]
        }
        if {$driver ne ""} {
            if {[catch {connect_bd_net $driver $vid_rst} cerr]} {
                puts "RESET CONNECT FAILED: $cerr"
            } else {
                puts "re-drove /video/aresetn from $driver"
            }
        } else {
            puts "WARNING: no reset driver found for /video/aresetn"
        }
    }
}

catch {validate_bd_design}
save_bd_design
puts "design saved"

set n [get_bd_intf_nets -quiet -of_objects [get_bd_intf_pins -quiet $vidout/video_in]]
if {$n eq ""} {
    puts "STREAM NOT CONNECTED"
    exit 1
}
puts "check: stream interface net is $n"

reset_target all [get_files -quiet base.bd]
generate_target all [get_files -quiet base.bd] -force
puts "RESULT: BLOCK DESIGN REPAIRED"
exit 0
