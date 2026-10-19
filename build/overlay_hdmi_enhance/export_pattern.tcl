# The previous run stopped at report_utilization because board/hdmi_pattern did
# not exist yet (the build script creates it after the reports). The bitstream
# itself was written successfully, so just export the artefacts.
set out_dir {C:/Users/79171/Desktop/FPGA/board/hdmi_pattern}
file mkdir $out_dir

cd {C:/Users/79171/Desktop/FPGA/build/overlay_hdmi_enhance/.work/tree/boards/Pynq-Z2/base}
open_project {base/base.xpr}
open_run impl_1
report_utilization    -file [file join $out_dir "util_impl.rpt"]
report_timing_summary -file [file join $out_dir "timing_impl.rpt"]
close_design

file copy -force [file join [pwd] base/base.runs/impl_1/base_wrapper.bit] [file join $out_dir "enhance_pattern.bit"]
file copy -force [file join [pwd] base/base.gen/sources_1/bd/base/hw_handoff/base.hwh] [file join $out_dir "enhance_pattern.hwh"]

puts "RESULT: EXPORT OK"
exit 0
