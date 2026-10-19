# -----------------------------------------------------------------------------
# Vitis HLS project for the streaming enhancer.
#
#   tools\env\vitis_hls.bat -f build\hls\enhance\run_hls.tcl
#
# Stages: C simulation -> C synthesis -> export Vivado IP.
# Same structure as build/hls/sobel/run_hls.tcl so there is one flow to remember.
# -----------------------------------------------------------------------------
set script_dir  [file dirname [file normalize [info script]]]
set repo_root   [file normalize [file join $script_dir ".." ".." ".."]]
set src_dir     [file join $repo_root "src" "hls" "enhance"]
set proj_dir    [file join $script_dir "proj"]
set report_dir  [file join $script_dir "reports"]

file mkdir $report_dir

open_project -reset $proj_dir
set_top enhance_stream
add_files [file join $src_dir "enhance.cpp"]
add_files -tb [file join $src_dir "tb_enhance.cpp"]

open_solution -reset "solution1"
set_part xc7z020clg400-1

# 7 ns = 142.86 MHz, the clock the PYNQ video fabric (clk_142M) runs at.
set clk_ns 7
foreach a $argv {
    if {[string is integer -strict $a]} {
        set clk_ns $a
        break
    }
}
puts "clock target: ${clk_ns} ns"
create_clock -period $clk_ns -name default

puts "=== CSIM ==="
if {[catch {csim_design} err]} {
    puts "CSIM FAILED: $err"
    exit 1
}

puts "=== CSYNTH ==="
if {[catch {csynth_design} err]} {
    puts "CSYNTH FAILED: $err"
    exit 1
}

foreach f {csynth.rpt} {
    set src [file join $proj_dir "solution1" "syn" "report" $f]
    if {[file exists $src]} {
        file copy -force $src [file join $report_dir $f]
    }
}

puts "=== EXPORT ==="
if {[catch {export_design -format ip_catalog -output [file join $script_dir "export" "enhance.zip"]} err]} {
    puts "EXPORT FAILED: $err"
    exit 1
}

puts "RESULT: OK"
exit 0
