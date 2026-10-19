open_project {C:/Users/79171/Desktop/FPGA/build/overlay_hdmi_enhance/.work/tree/boards/Pynq-Z2/base/base/base.xpr}

set xdc {C:/Users/79171/Desktop/FPGA/build/overlay_hdmi_enhance/cdc.xdc}
if {[llength [get_files -quiet $xdc]] == 0} {
    add_files -fileset constrs_1 -norecurse $xdc
    puts "added $xdc to constrs_1"
} else {
    puts "$xdc already in the project"
}

# The false paths reference block-design internals, so they only resolve once the
# BD is elaborated; report_timing_summary on the existing run would not see them.
# Re-running implementation with the extra constraints is what applies them.
puts "RESULT: CONSTRAINT ADDED"
exit 0
