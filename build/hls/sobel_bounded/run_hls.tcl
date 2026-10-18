# -----------------------------------------------------------------------------
# Vitis HLS project for the bounded (DMA-friendly) Sobel kernel.
#
#   tools\env\vitis_hls.bat -f build\hls\sobel_bounded\run_hls.tcl
#
# Same algorithm as the streaming kernel, but with ap_ctrl_hs + a pixel count, so
# the loop terminates and the pipeline drains before ap_done. That is what makes
# an AXI-DMA transfer able to close.
#
# Clock target: 10 ns (100 MHz), which is the clock the DMA overlay uses.
# -----------------------------------------------------------------------------
set script_dir  [file dirname [file normalize [info script]]]
set repo_root   [file normalize [file join $script_dir ".." ".." ".."]]
set src_dir     [file join $repo_root "src" "hls" "sobel"]
set proj_dir    [file join $script_dir "proj"]
set report_dir  [file join $script_dir "reports"]

file mkdir $report_dir

set clk_ns 10
foreach a $argv {
    if {[string is integer -strict $a]} {
        set clk_ns $a
        break
    }
}

open_project -reset $proj_dir
set_top sobel_bounded
add_files [file join $src_dir "sobel_bounded.cpp"]
add_files -tb [file join $src_dir "tb_sobel.cpp"]

open_solution -reset "solution1"
set_part xc7z020clg400-1
puts "clock target: ${clk_ns} ns"
create_clock -period $clk_ns -name default

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
if {[catch {export_design -format ip_catalog -output [file join $script_dir "export" "sobel_bounded.zip"]} err]} {
    puts "EXPORT FAILED: $err"
    exit 1
}

puts "RESULT: OK"
exit 0
