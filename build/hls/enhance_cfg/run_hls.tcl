# -----------------------------------------------------------------------------
# Vitis HLS project for the BRAM-configured enhancer.
#
#   tools\env\vitis_hls.bat -f build\hls\enhance_cfg\run_hls.tcl
#
# This variant is the same pipeline as build/hls/enhance (both include
# src/hls/enhance/enhance_body.inc), but it reads its nine configuration values from one
# 64-bit BRAM word on every pixel instead of taking them on plain ports.
#
# Why that matters: with plain ports HLS registers the values in the pipeline prologue, and
# a free-running kernel runs that prologue once - so a preset change needed a kernel reset,
# which interrupts the pixel stream. A memory read cannot be hoisted out of the loop, so the
# configuration stays live.
#
# C simulation is skipped here on purpose: tb_enhance.cpp drives the port-configured top
# function, which is already covered by build/hls/enhance. Behaviour equality between the two
# variants is guaranteed by the shared include, not by a second testbench.
# -----------------------------------------------------------------------------
set script_dir  [file dirname [file normalize [info script]]]
set repo_root   [file normalize [file join $script_dir ".." ".." ".."]]
set src_dir     [file join $repo_root "src" "hls" "enhance"]
set proj_dir    [file join $script_dir "proj"]
set report_dir  [file join $script_dir "reports"]

file mkdir $report_dir

open_project -reset $proj_dir
set_top enhance_stream_cfg
add_files [file join $src_dir "enhance.cpp"]
add_files [file join $src_dir "enhance_body.inc"]

open_solution -reset "solution1"
set_part xc7z020clg400-1
create_clock -period 7 -name default

puts "=== CSYNTH ==="
if {[catch {csynth_design} err]} {
    puts "CSYNTH FAILED: $err"
    exit 1
}

foreach f {csynth.rpt} {
    set src [file join $proj_dir "solution1" "syn" "report" $f]
    if {[file exists $src]} {
        file copy -force $src [file join $report_dir "cfg_$f"]
    }
}

puts "=== EXPORT ==="
if {[catch {export_design -format ip_catalog -output [file join $script_dir "export" "enhance_cfg.zip"]} err]} {
    puts "EXPORT FAILED: $err"
    exit 1
}

puts "RESULT: OK"
exit 0
