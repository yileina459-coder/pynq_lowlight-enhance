# Apply the HDMI input PLL range fix to the existing block design.
#
# Run on a project whose BD already has the kernel inserted, so only implementation
# has to be redone. (Rebuilding from base.tcl instead throws away Vivado's per-project
# IP cache and re-synthesises ~200 out-of-context runs - about an hour.)
#
# The first attempt at this used
#     get_bd_cells -quiet -filter {NAME =~ "*dvi2rgb*"}
# which matches nothing: get_bd_cells only returns top-level cells unless
# -hierarchical is given, and dvi2rgb lives inside the video hierarchy. The property
# was never set and the build reproduced the old design.
#
# Why range 2: dvi2rgb.vhd says "MULT_F = kClkRange*5 (choose >=120MHz=1, >=60MHz=2,
# >=40MHz=3)". The stock design uses 1 (>=120 MHz) while its EDID advertises 720p
# (TMDS clock 74.25 MHz) - MULT_F would be 5, VCO 371 MHz, below the MMCM minimum,
# so the input PLL can never lock. Range 2 covers 60-120 MHz.

set base_dir [lindex $argv end]

if {$base_dir eq ""} {
    puts "usage: fix_clkrange_only.tcl <base_dir>"
    exit 1
}

cd $base_dir
open_project {base/base.xpr}
open_bd_design {base/base.srcs/sources_1/bd/base/base.bd}

set cells [get_bd_cells -hierarchical -filter {NAME =~ "*dvi2rgb*"}]
puts "matched cells: $cells"
if {[llength $cells] == 0} {
    puts "ERROR: no dvi2rgb cell found even with -hierarchical"
    exit 1
}

foreach cell $cells {
    set before [get_property -quiet CONFIG.kClkRange $cell]
    set_property -dict [list CONFIG.kClkRange {2}] $cell
    set after [get_property -quiet CONFIG.kClkRange $cell]
    puts "  $cell : kClkRange $before -> $after"
}

validate_bd_design
save_bd_design
puts "RESULT: CLKRANGE FIXED"
exit 0
