# C simulation for the memory-configured kernel.
#
#   tools\env\vitis_hls.bat -f build\hls\enhance_cfg\csim.tcl
#
# The pixel maths is shared with the port-based variant and covered by its testbench, but the
# configuration path is unique to this kernel and is exactly where a real defect lived: with the
# word read straight from memory on every pixel, any preset with gain != 1.0 striped the picture.
# The kernel now latches the word once per line, and this checks that latch.

set script_dir  [file dirname [file normalize [info script]]]
set repo_root   [file normalize [file join $script_dir ".." ".." ".."]]
set src_dir     [file join $repo_root "src" "hls" "enhance"]
set proj_dir    [file join $script_dir "csim"]

open_project -reset $proj_dir
set_top enhance_stream_cfg
add_files [file join $src_dir "enhance.cpp"] -cflags "-DENH_EMU_PIXELS=307200"
add_files -tb [file join $src_dir "tb_enhance_cfg.cpp"]
add_files -tb [file join $src_dir "enhance_tb_support.cpp"]

open_solution -reset "solution1"
set_part xc7z020clg400-1
create_clock -period 7 -name default

puts "=== CSIM ==="
if {[catch {csim_design -clean} err]} {
    puts "CSIM FAILED: $err"
    exit 1
}
puts "RESULT: CSIM OK"
exit 0
