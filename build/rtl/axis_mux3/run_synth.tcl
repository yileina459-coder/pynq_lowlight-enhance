# -----------------------------------------------------------------------------
# Synthesis check for the hand-written operator selector.
#
# Functional simulation with xsim is blocked in this environment (the kernel
# aborts at startup with "Could not open file mapping object" ->
# EXCEPTION_ACCESS_VIOLATION, before any testbench code runs; xvlog and xelab
# both succeed). Synthesis still proves the RTL is legal, gives its resource
# cost and shows whether it can meet the 7 ns video clock, so that is what this
# script does.
#
#   tools\env\vivado.bat -mode batch -nojournal -nolog -source build\rtl\axis_mux3\run_synth.tcl
# -----------------------------------------------------------------------------
set script_dir [file dirname [file normalize [info script]]]
set repo_root  [file normalize [file join $script_dir ".." ".." ".."]]
set src_dir    [file join $repo_root "src" "rtl" "axis_mux3"]
set proj_dir   [file join $script_dir "synth_proj"]
set out_dir    [file join $script_dir ".." ".." ".." "build" "rtl" "axis_mux3"]

create_project -force mux3_synth $proj_dir -part xc7z020clg400-1
add_files -norecurse [file join $src_dir "axis_mux3.v"]
set_property top axis_mux3 [current_fileset]

puts "=== SYNTH (7 ns, the video clock) ==="
synth_design -top axis_mux3 -part xc7z020clg400-1
create_clock -period 7 -name ap_clk [get_ports aclk]
report_utilization -file [file join $out_dir "mux3_util.rpt"]
report_timing_summary -file [file join $out_dir "mux3_timing.rpt"]

puts "RESULT: OK"
exit 0
