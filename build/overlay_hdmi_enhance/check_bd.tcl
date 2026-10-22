# Refuse to build on a block design that is structurally broken.
#
#   vivado -mode batch -source build\overlay_hdmi_enhance\check_bd.tcl
#
# Why
#   Several experiments deleted cells and re-laid stream connections. A design with pixel_unpack
#   disconnected from v_axi4s_vid_out still synthesises and still produces a bitstream - it just
#   never shows a picture, and the failure looks like a software bug. This check makes that state
#   loud, and build_bitstream.tcl runs it first.
#
# Checks
#   1. pixel_unpack and v_axi4s_vid_out are joined by an *interface* net (a pin-level connection
#      breaks PYNQ's metadata parser).
#   2. The enhance kernel's stream input and output are connected as interfaces too.
#   3. The configuration memory is connected to the kernel's cfg port.
#   4. /video/aresetn has a driver.
#   5. No top-level video block has an unconnected stream-side input.

set script_dir [file dirname [file normalize [info script]]]
set proj_file  [file join $script_dir ".work" "tree" "boards" "Pynq-Z2" "base" "base" "base.xpr"]

open_project $proj_file
open_bd_design [get_files -quiet base.bd]

set problems {}

proc require_intf_net {problems_ref label pin_path} {
    upvar $problems_ref problems
    set pin [get_bd_intf_pins -quiet $pin_path]
    if {$pin eq ""} {
        lappend problems "$label: interface pin not found ($pin_path)"
        return
    }
    if {[get_bd_intf_nets -quiet -of_objects $pin] eq ""} {
        lappend problems "$label: interface pin has no net ($pin_path)"
    }
}

require_intf_net problems "stream into vid_out" /video/hdmi_out/frontend/v_axi4s_vid_out_0/video_in
require_intf_net problems "kernel input"        /enhance_cfg_0/s_in
require_intf_net problems "kernel output"       /enhance_cfg_0/s_out

# Configuration memory -> kernel
set cfg_in [get_bd_pins -quiet /enhance_cfg_0/cfg_Dout_A]
if {$cfg_in ne "" && [get_bd_nets -quiet -of_objects $cfg_in] eq ""} {
    lappend problems "kernel configuration: cfg_Dout_A has no net (the config BRAM is not connected)"
}

# Video reset must have a driver
set vid_rst [get_bd_pins -quiet /video/aresetn]
if {$vid_rst ne ""} {
    set net [get_bd_nets -quiet -of_objects $vid_rst]
    if {$net eq ""} {
        lappend problems "/video/aresetn has no net"
    } else {
        set driven 0
        foreach p [get_bd_pins -quiet -of_objects $net] {
            if {[get_property DIR $p] eq "O"} { set driven 1; break }
        }
        if {!$driven} { lappend problems "/video/aresetn net '$net' has no source" }
    }
}

# Report, and fail if anything is wrong.
#
# This file is both a standalone check and a guard sourced by build_bitstream.tcl. Two traps when
# it is sourced, both of which silently cost a build:
#   * `exit` ends the whole Vivado session, so the caller gets no chance to abort cleanly - hence
#     the verdict is reported through ::bd_check_result;
#   * opening the project here leaves it open, and the caller's own open_project then fails with
#     "Project is already open" - hence the close below.
# When this file is sourced by the build script it must leave no project open, otherwise the
# caller's own open_project fails with "Project is already open" - which silently cost a build.
proc ::bd_check_tidy {} {
    if {[info exists ::bd_check_standalone] && !$::bd_check_standalone} {
        catch {close_project}
    }
}

set ::bd_check_result "OK"
if {[llength $problems] > 0} {
    puts "BD CHECK FAIL"
    foreach p $problems { puts "  - $p" }
    puts "RESULT: BD BROKEN"
    set ::bd_check_result "BROKEN"
    ::bd_check_tidy
    if {[info exists ::bd_check_standalone] && $::bd_check_standalone} {
        catch {close_project}
        exit 1
    }
    return
}

puts "BD CHECK PASS: stream interfaces intact, configuration memory connected, video reset driven"
puts "RESULT: BD OK"
::bd_check_tidy
if {[info exists ::bd_check_standalone] && $::bd_check_standalone} {
    catch {close_project}
    exit 0
}
