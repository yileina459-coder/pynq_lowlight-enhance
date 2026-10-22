# -----------------------------------------------------------------------------
# Vitis HLS project for the SOF generator.
#
#   tools\env\vitis_hls.bat -f build\hls\sof_gen\run_hls.tcl
#
# The kernel is a one-stage AXI4-Stream passthrough that replaces TUSER with a generated
# frame-start marker. It is built in HLS rather than as plain RTL so the block design keeps the
# stream as an *interface*: the RTL version used individual pins, which broke the interface bridge
# between pixel_unpack and v_axi4s_vid_out and made PYNQ refuse the overlay.
#
# C simulation is skipped; the behaviour is a two-state counter and is covered by
# tools/check_sof_gen.py against the source, plus the on-board measurement of the resulting offset.
# -----------------------------------------------------------------------------
set script_dir  [file dirname [file normalize [info script]]]
set repo_root   [file normalize [file join $script_dir ".." ".." ".."]]
set src_dir     [file join $repo_root "src" "hls" "sof_gen"]
set proj_dir    [file join $script_dir "proj"]
set report_dir  [file join $script_dir "reports"]

file mkdir $report_dir

open_project -reset $proj_dir
set_top sof_gen
add_files [file join $src_dir "sof_gen.cpp"]

open_solution -reset "solution1"
set_part xc7z020clg400-1

# 7 ns matches the pixel clock domain the module lives in (142.86 MHz).
create_clock -period 7 -name default

puts "=== CSYNTH ==="
if {[catch {csynth_design} err]} {
    puts "CSYNTH FAILED: $err"
    exit 1
}

foreach f {csynth.rpt} {
    set src [file join $proj_dir "solution1" "syn" "report" $f]
    if {[file exists $src]} {
        file copy -force $src [file join $report_dir "sof_$f"]
    }
}

puts "=== EXPORT ==="
if {[catch {export_design -format ip_catalog -output [file join $script_dir "export" "sof_gen.zip"]} err]} {
    puts "EXPORT FAILED: $err"
    exit 1
}

puts "RESULT: OK"
exit 0
