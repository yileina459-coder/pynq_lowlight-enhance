# -----------------------------------------------------------------------------
# Implement and export the HDMI overlay (enhance variant).
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
set out_dir    [file join $repo_root "board" "hdmi_stream_enhance"]

# Structural gate: a block design whose stream interfaces are broken still synthesises and still
# produces a bitstream - it just never shows a picture, and the failure looks like a software bug.
# Several block-design experiments had to be repaired, so the check runs first and refuses here.
#
# check_bd.tcl only calls exit when it is run standalone; with this flag set it returns and reports
# through ::bd_check_result. (It used to exit unconditionally, which ended this session at the gate
# and silently skipped an entire build - the log looked like a success.)
set ::bd_check_standalone 0
catch {source [file join $script_dir "check_bd.tcl"]} bd_err
unset -nocomplain ::bd_check_standalone
if {![info exists ::bd_check_result] || $::bd_check_result ne "OK"} {
    puts "BD STRUCTURE BROKEN - refusing to build ($bd_err)"
    exit 1
}
puts "block design verified; starting the build"

cd $work
# The structural gate above opens this same project to inspect the block design; tolerate that
# rather than dying with "Project is already open", which silently skipped two builds.
if {[llength [current_project -quiet]] == 0} {
    open_project {base/base.xpr}
} else {
    puts "project already open; continuing with it"
}

# Out-of-context synthesis: ~200 IPs, one run each.
#
# Two failure modes were hit here, both documented so the next person does not
# repeat them:
#
# 1. Parallel runs collide in Vivado's Tcl app store.
#    With -jobs 4 several child processes load the app store at once and die:
#        ERROR: [Common 17-354] Could not open 'C' for writing.
#        ERROR: [Common 17-39] 'tclapp::load_apps' failed due to earlier errors.
#    -jobs 1 avoids it but is unusably slow (200 runs, serialised).
#
# 2. Switching IPs to global synthesis is the "right" fix in principle, but for
#    IPs that live inside a block design `get_ips` returns nothing here, so the
#    property never gets applied (the counter below prints 0). To make it work
#    you would have to reach the IPs through the BD hierarchy.
#
# What actually works: run with a low job count so that only the handful of
# still-missing runs execute. Everything already synthesised is reused from the
# IP cache, so a retry after a failure converges quickly (in this build: 4
# outstanding runs, ~15 minutes to a bitstream).
set n_none 0
foreach ip [get_ips] {
    if {[catch {set_property synth_checkpoint_mode None $ip} err]} {
        puts "note: could not set global synth for $ip: $err"
    } else {
        incr n_none
    }
}
puts "IPs switched to global synthesis: $n_none (0 is expected for IPs inside the block design)"

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

set jobs 2
if {[info exists ::env(HDMI_JOBS)]} {
    set jobs $::env(HDMI_JOBS)
}
puts "parallel jobs: $jobs"

puts "=== IMPLEMENTATION ==="
reset_run synth_1
reset_run impl_1
launch_runs impl_1 -to_step write_bitstream -jobs $jobs
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

file copy -force [file join $work "base" "base.runs" "impl_1" "base_wrapper.bit"] [file join $out_dir "enhance_hdmi.bit"]
file copy -force [file join $work "base" "base.gen" "sources_1" "bd" "base" "hw_handoff" "base.hwh"] [file join $out_dir "enhance_hdmi.hwh"]

puts "RESULT: OK"
exit 0
