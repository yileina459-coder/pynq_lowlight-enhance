# Connect the SOF generator's reset, which the insertion left dangling.
#
#   vivado -mode batch -source build\overlay_hdmi_enhance\fix_sof_reset2.tcl
#
# Why this matters more than it looks
#   An HLS kernel with ap_ctrl_none still needs ap_rst_n. With the pin unconnected the generated RTL
#   held the datapath in reset, so the kernel never accepted a pixel: the VDMA stopped being consumed
#   and PYNQ raised "RuntimeError: DMA channel not started" in the demo, exactly like a design with a
#   broken stream path. The insertion script tried to take the net off the video core's aresetn pin,
#   which is a hierarchy-local net and did not resolve, and it silently did nothing.
#
#   Here the reset comes from /video/aresetn - the same reset the video blocks are given - and the
#   result is verified rather than assumed.

set script_dir [file dirname [file normalize [info script]]]
set proj_file  [file join $script_dir ".work" "tree" "boards" "Pynq-Z2" "base" "base" "base.xpr"]

open_project $proj_file
open_bd_design [get_files -quiet base.bd]

set sof [get_bd_cells -quiet /video/hdmi_out/sof_gen_0]
if {$sof eq ""} { puts "ERROR: no sof_gen_0"; exit 1 }

set rst_pin [get_bd_pins -quiet $sof/ap_rst_n]
if {$rst_pin eq ""} { puts "ERROR: no ap_rst_n pin"; exit 1 }

# Which reset does the design actually use for the video domain?
set candidates [list /video/aresetn /rst_ps7_0_fclk1/peripheral_aresetn]
set done 0
foreach candidate $candidates {
    set pin [get_bd_pins -quiet $candidate]
    if {$pin eq ""} { continue }
    set net [get_bd_nets -quiet -of_objects $pin]
    if {$net eq ""} {
        puts "$candidate exists but has no net"
        continue
    }
    if {[catch {connect_bd_net $net $rst_pin} cerr]} {
        puts "connect via $candidate failed: $cerr"
        continue
    }
    puts "connected $candidate ($net) -> sof_gen_0/ap_rst_n"
    set done 1
    break
}

if {!$done} {
    # Last resort: the hier pin /video/aresetn itself may be driven from outside, so connect to it
    # directly - connect_bd_net accepts a pin and a net in either order.
    set hier [get_bd_pins -quiet /video/aresetn]
    if {$hier ne ""} {
        if {[catch {connect_bd_net $hier $rst_pin} cerr]} {
            puts "ERROR: could not connect the reset: $cerr"
        } else {
            puts "connected /video/aresetn -> sof_gen_0/ap_rst_n"
            set done 1
        }
    }
}

if {!$done} { puts "ERROR: reset left unconnected"; exit 1 }

catch {validate_bd_design}
save_bd_design

# Verify, because "it printed connected" was true last time as well.
set check [get_bd_nets -quiet -of_objects [get_bd_pins -quiet $sof/ap_rst_n]]
if {$check eq ""} {
    puts "RESULT: RESET STILL DANGLING"
    exit 1
}
puts "verified: ap_rst_n is on net $check"

reset_target all [get_files -quiet base.bd]
generate_target all [get_files -quiet base.bd] -force
puts "RESULT: SOF RESET CONNECTED"
exit 0
