# Minimal toolchain + license smoke test for XC7Z020 (PYNQ-Z2)
set script_dir [file dirname [file normalize [info script]]]
set proj_dir [file join $script_dir "proj"]

create_project -force smoke $proj_dir -part xc7z020clg400-1
add_files -norecurse [file join $script_dir "smoke_top.v"]
set_property top smoke_top [get_filesets sources_1]

puts "=== SYNTH START ==="
synth_design -top smoke_top -part xc7z020clg400-1
puts "=== SYNTH DONE ==="

report_utilization -file [file join $script_dir "util_smoke.rpt"]
puts "RESULT: OK"
