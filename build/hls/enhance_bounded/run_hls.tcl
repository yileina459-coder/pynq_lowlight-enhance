# -----------------------------------------------------------------------------
# Vitis HLS project for the bounded (DMA-friendly) enhance kernel.
#
#   tools\env\vitis_hls.bat -f build\hls\enhance_bounded\run_hls.tcl
#
# Same arithmetic as enhance_stream, but with ap_ctrl_hs, a pixel count and the
# 59 config bits on AXI-Lite. That combination is what the DMA path needs: the
# loop terminates, the pipeline drains, and the PS can set a preset per frame.
#
# No csim stage here on purpose: the streaming variant is the one covered by
# tb_enhance.cpp, and the two share the same stage-by-stage maths. The bounded
# variant is instead proven on the board, by comparing the DMA readback against
# the numpy golden model with zero tolerance - a stronger check than csim.
#
# Clock target: 10 ns, the clock the DMA overlay runs at.
# -----------------------------------------------------------------------------
set script_dir [file dirname [file normalize [info script]]]
set repo_root  [file normalize [file join $script_dir ".." ".." ".."]]
set src_dir    [file join $repo_root "src" "hls" "enhance"]
set proj_dir   [file join $script_dir "proj"]
set report_dir [file join $script_dir "reports"]

file mkdir $report_dir

set clk_ns 10
foreach a $argv {
    if {[string is integer -strict $a]} {
        set clk_ns $a
        break
    }
}

open_project -reset $proj_dir
set_top enhance_bounded
add_files [file join $src_dir "enhance_bounded.cpp"]

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
if {[catch {export_design -format ip_catalog -output [file join $script_dir "export" "enhance_bounded.zip"]} err]} {
    puts "EXPORT FAILED: $err"
    exit 1
}

puts "RESULT: OK"
exit 0
