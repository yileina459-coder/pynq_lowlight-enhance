# Pin the whole design to 640x480@60.
#
# Measured on the board (2026-10-22): with the unmodified overlay at 640x480 the VDMA
# consumed a frame immediately and the capture card showed the picture; at 720p and
# 1080p no frame was ever consumed and no TMDS appeared. So the output hardware works
# and the limit is the pixel clock.
#
# Clock maths for 640x480 (25.175 MHz pixel clock, 125.9 MHz serial):
#     dvi2rgb kClkRange=5 -> VCO = 25.175 * 25 = 629.4 MHz   (600-1200, valid)
#     kClkRange=4 would give 503 MHz, below the MMCM minimum, hence 5.
#     rgb2dvi does not use kClkRange at all here: kGenerateSerialClk=false, so its
#     serial clock comes from axi_dynclk's PXL_CLK_5X_O.
#
# The EDID also has to advertise 640x480 and nothing higher, including clearing the
# established-timing bitmap (1024x768 lives there and Windows would prefer it).
# tools/make_edid_640x480.py produces it; the IP only accepts its own four file names,
# so it is installed as 720p_edid.data.

set base_dir [lindex $argv end]
if {$base_dir eq ""} { puts "usage: pin_640x480.tcl <base_dir>"; exit 1 }

set edid_src {C:/Users/79171/Desktop/FPGA/src/rtl/edid/edid_640x480.data}
set edid_dst {C:/Users/79171/Desktop/FPGA/build/overlay_hdmi_enhance/.work/tree/boards/ip/dvi2rgb_v1_7/src/720p_edid.data}
file copy -force $edid_src $edid_dst
puts "installed EDID: $edid_dst"

cd $base_dir
open_project {base/base.xpr}
open_bd_design {base/base.srcs/sources_1/bd/base/base.bd}

foreach cell [get_bd_cells -hierarchical -filter {NAME =~ "*dvi2rgb*"}] {
    set_property -dict [list \
        CONFIG.kClkRange {5} \
        CONFIG.kEdidFileName {720p_edid.data} \
    ] $cell
    puts "  $cell : kClkRange=[get_property CONFIG.kClkRange $cell] kEdidFileName=[get_property CONFIG.kEdidFileName $cell]"
}

validate_bd_design
save_bd_design
puts "RESULT: PINNED TO 640x480"
exit 0
