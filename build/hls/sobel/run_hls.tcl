# -----------------------------------------------------------------------------
# Vitis HLS project for the streaming Sobel kernel.
#
#   tools\env\vitis_hls.bat -f build\hls\sobel\run_hls.tcl
#
# Stages: C simulation -> C synthesis -> export Vivado IP.
# Artefacts land next to this script in proj\ and export\ (both git-ignored);
# the numbers we care about are printed to the log and copied into
# build\hls\sobel\reports\ by the -post-hook below.
# -----------------------------------------------------------------------------
set script_dir  [file dirname [file normalize [info script]]]
set repo_root   [file normalize [file join $script_dir ".." ".." ".."]]
set src_dir     [file join $repo_root "src" "hls" "sobel"]
set proj_dir    [file join $script_dir "proj"]
set report_dir  [file join $script_dir "reports"]

file mkdir $report_dir

open_project -reset $proj_dir
set_top sobel_stream
add_files [file join $src_dir "sobel.cpp"]
add_files -tb [file join $src_dir "tb_sobel.cpp"]

open_solution -reset "solution1"
set_part xc7z020clg400-1
# 10 ns = 100 MHz. A 720p60 stream needs a 74.25 MHz pixel clock, so closing at
# 100 MHz leaves headroom for the rest of the pipeline.
create_clock -period 10 -name default

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

# Keep the evidence that matters for the report next to the script.
foreach f {csynth.rpt} {
    set src [file join $proj_dir "solution1" "syn" "report" $f]
    if {[file exists $src]} {
        file copy -force $src [file join $report_dir $f]
    }
}

puts "=== EXPORT ==="
if {[catch {export_design -format ip_catalog -output [file join $script_dir "export" "sobel.zip"]} err]} {
    puts "EXPORT FAILED: $err"
    exit 1
}

puts "RESULT: OK"
exit 0
