# -----------------------------------------------------------------------------
# Vitis HLS project for the streaming sharpen kernel.
#
#   tools\env\vitis_hls.bat -f build\hls\sharpen\run_hls.tcl
#
# Same stages as the other kernels: C simulation -> C synthesis -> export IP.
# Default clock target is 7 ns (142.86 MHz), the PYNQ video fabric clock.
# -----------------------------------------------------------------------------
set script_dir  [file dirname [file normalize [info script]]]
set repo_root   [file normalize [file join $script_dir ".." ".." ".."]]
set src_dir     [file join $repo_root "src" "hls" "sharpen"]
set proj_dir    [file join $script_dir "proj"]
set report_dir  [file join $script_dir "reports"]

file mkdir $report_dir

set clk_ns 7
foreach a $argv {
    if {[string is integer -strict $a]} {
        set clk_ns $a
        break
    }
}

open_project -reset $proj_dir
set_top sharpen_stream
add_files [file join $src_dir "sharpen.cpp"]
add_files -tb [file join $src_dir "tb_sharpen.cpp"]

open_solution -reset "solution1"
set_part xc7z020clg400-1
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

set src [file join $proj_dir "solution1" "syn" "report" "csynth.rpt"]
if {[file exists $src]} {
    file copy -force $src [file join $report_dir "csynth.rpt"]
}

puts "=== EXPORT ==="
if {[catch {export_design -format ip_catalog -output [file join $script_dir "export" "sharpen.zip"]} err]} {
    puts "EXPORT FAILED: $err"
    exit 1
}

puts "RESULT: OK"
exit 0
