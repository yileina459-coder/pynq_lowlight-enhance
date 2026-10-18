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

# Clock target, in ns. Optional first tclarg, defaults to 7 ns.
#
#   7 ns  = 142.86 MHz - the clock the PYNQ video fabric (clk_142M) actually
#          runs at, so the kernel can be dropped straight into the HDMI path.
#   10 ns = 100 MHz  - the DMA overlay clock.
# Building for the faster target covers both: an IP that closes at 142.86 MHz
# also closes at 100 MHz, so there is one IP variant to maintain.
set clk_ns 7
# vitis_hls puts its own switches ("-f", the script name, ...) in $argv, so look
# for the first integer rather than assuming a position.
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
