# Pin the whole design to 720p60, including the EDID the sink advertises.
#
# Why 720p
#   74.25 MHz pixel clock is the only mode where every PLL is inside range with one
#   kClkRange value:
#       dvi2rgb  kClkRange=2 -> VCO = 74.25 * 10 = 742.5 MHz  (600-1200, valid)
#       rgb2dvi  kClkRange=2 -> VCO = 74.25 * 10 = 742.5 MHz  (600-1200, valid)
#   1080p needs range 1 on both (148.5 * 5 = 742.5), 900p needs 108 MHz and works at
#   range 2, but Windows picks 1080p whenever it is advertised - and 1080p is exactly
#   the mode that has never produced TMDS here.
#
# Why the EDID has to be overwritten rather than renamed
#   dvi2rgb's kEdidFileName is an enum of the four files that ship with the IP
#   ("Value '720p_only_edid.data' is out of the range for parameter
#   'Preferred resolution(kEdidFileName)'"), and all four contain 1920x1080 in their
#   standard timings. So the only way to stop Windows offering 1080p is to replace the
#   contents of an accepted filename - we replace 720p_edid.data, keeping its 1280x720
#   detailed timing and clearing the standard timing list (see
#   tools/make_edid_720p_only.py).
#
#   NOTE: this edits the cloned PYNQ tree, so a fresh build.bat fetch restores the
#   stock EDID. Run this script again after any re-fetch.

set base_dir [lindex $argv end]
if {$base_dir eq ""} { puts "usage: pin_720p.tcl <base_dir>"; exit 1 }

set edid_src {C:/Users/79171/Desktop/FPGA/src/rtl/edid/720p_only_edid.data}
set edid_dst {C:/Users/79171/Desktop/FPGA/build/overlay_hdmi_enhance/.work/tree/boards/ip/dvi2rgb_v1_7/src/720p_edid.data}
file copy -force $edid_src $edid_dst
puts "replaced EDID: $edid_dst"

cd $base_dir
open_project {base/base.xpr}
open_bd_design {base/base.srcs/sources_1/bd/base/base.bd}

foreach cell [get_bd_cells -hierarchical -filter {NAME =~ "*dvi2rgb*"}] {
    set_property -dict [list \
        CONFIG.kClkRange {2} \
        CONFIG.kEdidFileName {720p_edid.data} \
    ] $cell
    puts "  $cell : kClkRange=[get_property CONFIG.kClkRange $cell] kEdidFileName=[get_property CONFIG.kEdidFileName $cell]"
}
foreach cell [get_bd_cells -hierarchical -filter {NAME =~ "*rgb2dvi*"}] {
    set_property -dict [list CONFIG.kClkRange {2}] $cell
    puts "  $cell : kClkRange=[get_property CONFIG.kClkRange $cell]"
}

validate_bd_design
save_bd_design
puts "RESULT: PINNED TO 720P"
exit 0
