# Revert to the external-input design and fix the *output* PLL range.
#
# Two changes, both needed before the next implementation run:
#
# 1. Remove the internal pattern generator again. It was inserted for a diagnostic and
#    the design has to take its video from the HDMI input for the passthrough.
#
# 2. Set rgb2dvi's kClkRange to 2 so input and output both support 720p60.
#    ClockGen.vhd documents the same rule as dvi2rgb:
#        MULT_F = kClkRange*5, CLKOUT0_DIVIDE_F = kClkRange, CLKIN1_PERIOD = kClkRange*6
#    so the VCO is (kClkRange * 5) x pixel clock:
#        720p60 :  74.25 MHz x 10 = 742.5 MHz -> valid with kClkRange = 2
#    The board EDID and the supported input path target 720p60, so both ends must
#    use range 2. Range 1 made the output PLL invalid at 720p even when input locked.

set base_dir [lindex $argv end]
if {$base_dir eq ""} { puts "usage: fix_output_range.tcl <base_dir>"; exit 1 }

cd $base_dir
open_project {base/base.xpr}
open_bd_design {base/base.srcs/sources_1/bd/base/base.bd}

# --- 1. drop the pattern generator, restore the input -----------------------
if {[llength [get_bd_cells -quiet /vpg_0]] > 0} {
    puts "deleting /vpg_0"
    delete_bd_objs [get_bd_cells /vpg_0]
}
set stamp_in [get_bd_cells -quiet /stamp_in_0]
if {[llength $stamp_in] == 0} {
    puts "ERROR: stamp_in_0 missing"
    exit 1
}
set existing [get_bd_intf_nets -quiet -of_objects [get_bd_intf_pins stamp_in_0/s_axis]]
if {[llength $existing] == 0} {
    puts "reconnecting the HDMI input stream into stamp_in_0"
    connect_bd_intf_net [get_bd_intf_pins video/hdmi_in/out_stream] \
                        [get_bd_intf_pins stamp_in_0/s_axis]
} else {
    puts "input stream already connected to stamp_in_0"
}

# --- 2. correct the output clock range --------------------------------------
set divs [get_bd_cells -hierarchical -filter {NAME =~ "*rgb2dvi*"}]
puts "matched: $divs"
if {[llength $divs] == 0} {
    puts "ERROR: no rgb2dvi cell found"
    exit 1
}
foreach cell $divs {
    set before [get_property -quiet CONFIG.kClkRange $cell]
    set_property -dict [list CONFIG.kClkRange {2}] $cell
    puts "  $cell : kClkRange $before -> [get_property CONFIG.kClkRange $cell]"
}

assign_bd_address
validate_bd_design
save_bd_design
puts "RESULT: OUTPUT RANGE FIXED"
exit 0
