# -----------------------------------------------------------------------------
# Simulate the operator selector with xsim.
#
#   tools\env\vivado.bat -mode batch -nojournal -nolog -source build\rtl\axis_mux3\run_sim.tcl
#
# Compiles axis_mux3.v together with its self-checking testbench, runs it and
# fails the build if the testbench reports an error.
# -----------------------------------------------------------------------------
set script_dir [file dirname [file normalize [info script]]]
set repo_root  [file normalize [file join $script_dir ".." ".." ".."]]
set src_dir    [file join $repo_root "src" "rtl" "axis_mux3"]
set work_dir   [file join $script_dir "xsim"]

file mkdir $work_dir
cd $work_dir

puts "=== COMPILE ==="
if {[catch {
    exec xvlog [file join $src_dir "axis_mux3.v"] [file join $src_dir "tb_axis_mux3.v"]
} err]} {
    puts "XVLOG FAILED: $err"
    exit 1
}

puts "=== ELABORATE ==="
if {[catch {exec xelab -debug typical tb_axis_mux3 -s mux3_sim} err]} {
    puts "XELAB FAILED: $err"
    exit 1
}

puts "=== RUN ==="
set rc [catch {exec xsim mux3_sim -runall} out]
puts $out
if {$rc} {
    puts "XSIM FAILED"
    exit 1
}
if {[string first "AXIS_MUX3 TB PASS" $out] < 0} {
    puts "TESTBENCH DID NOT PASS"
    exit 1
}

puts "RESULT: OK"
exit 0
