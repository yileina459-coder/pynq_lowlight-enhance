# -----------------------------------------------------------------------------
# Implement and export the HDMI overlay.
#
# This replaces PYNQ's own build_bitstream.tcl in our flow. Differences:
#   * -jobs 1: the stock script uses 4 parallel runs. On this machine the
#     out-of-context synthesis runs failed with
#       ERROR: [Common 17-1257] Failed to create directory 'C'.
#       ERROR: [Common 17-39] 'tclapp::load_apps' failed
#     which is Vivado's Tcl app store being written by several child processes
#     at once. Serialising the runs costs wall-clock time but removes the race.
#   * exports both the .bit and the .hwh with one base name, which is what PYNQ
#     needs, and copies them to board/hdmi_stream.
# -----------------------------------------------------------------------------
set script_dir [file dirname [file normalize [info script]]]
set repo_root  [file normalize [file join $script_dir ".." ".."]]
set work       [file join $script_dir ".work" "tree" "boards" "Pynq-Z2" "base"]
set out_dir    [file join $repo_root "board" "hdmi_stream"]

cd $work
open_project {base/base.xpr}

set bd_file [get_files base.bd]
generate_target all $bd_file
make_wrapper -files $bd_file -top

set wrapper [file join $work "base" "base.gen" "sources_1" "bd" "base" "hdl" "base_wrapper.v"]
if {![file exists $wrapper]} {
    error "wrapper not generated: $wrapper"
}
if {[llength [get_files -quiet $wrapper]] == 0} {
    add_files -norecurse $wrapper
}
set_property top base_wrapper [current_fileset]
import_files -fileset constrs_1 -norecurse [file join $work "vivado" "constraints" "base.xdc"]
update_compile_order -fileset sources_1

puts "=== IMPLEMENTATION (jobs 1, 30-50 min) ==="
reset_run impl_1
launch_runs impl_1 -to_step write_bitstream -jobs 1
wait_on_run impl_1

set status [get_property STATUS [get_runs impl_1]]
puts "impl_1 status: $status"
if {[string first "write_bitstream Complete" $status] < 0} {
    error "implementation failed: $status"
}

open_run impl_1
report_utilization    -file [file join $out_dir "util_impl.rpt"]
report_timing_summary -file [file join $out_dir "timing_impl.rpt"]
close_design

puts "=== EXPORT ==="
file mkdir $out_dir
set xsa [file join $out_dir "base.xsa"]
write_hw_platform -fixed -force -include_bit $xsa
validate_hw_platform $xsa

file copy -force [file join $work "base" "base.runs" "impl_1" "base_wrapper.bit"] [file join $out_dir "sobel_hdmi.bit"]
file copy -force [file join $work "base" "base.gen" "sources_1" "bd" "base" "hw_handoff" "base.hwh"] [file join $out_dir "sobel_hdmi.hwh"]

puts "RESULT: OK"
exit 0
