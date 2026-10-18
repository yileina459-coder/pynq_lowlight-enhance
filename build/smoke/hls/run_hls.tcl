# Vitis HLS 2026.1 smoke test: C sim + C synth + export IP
set script_dir [file dirname [file normalize [info script]]]
set proj [file join $script_dir "proj"]

open_project -reset $proj
set_top stream_smoke
add_files [file join $script_dir "src" "stream_smoke.cpp"]
add_files -tb [file join $script_dir "src" "tb_stream_smoke.cpp"]

open_solution -reset "solution1" -flow_target vivado
set_part xc7z020clg400-1
create_clock -period 10 -name default

puts "=== CSIM ==="
if {[catch {csim_design -clean} err]} {
    puts "CSIM FAILED: $err"
    exit 1
}

puts "=== CSYNTH ==="
if {[catch {csynth_design} err]} {
    puts "CSYNTH FAILED: $err"
    exit 1
}

puts "=== EXPORT ==="
if {[catch {export_design -format ip_catalog -output [file join $script_dir "export" "stream_smoke.zip"]} err]} {
    puts "EXPORT FAILED: $err"
    exit 1
}

puts "RESULT: OK"
exit 0
