# Finish the SOF wiring: tie the unused tuser input, validate, save, regenerate.
#
#   vivado -mode batch -source build\overlay_hdmi_enhance\finalize_sof.tcl

set script_dir [file dirname [file normalize [info script]]]
set proj_file  [file join $script_dir ".work" "tree" "boards" "Pynq-Z2" "base" "base" "base.xpr"]

open_project $proj_file
open_bd_design [get_files -quiet base.bd]

set sof    [get_bd_cells -quiet /sof_gen_0]
set unpack [get_bd_cells -quiet /video/hdmi_out/pixel_unpack]

set upstream_tuser [get_bd_pins -quiet $unpack/stream_out_24_TUSER]
set sof_tuser      [get_bd_pins -quiet $sof/s_tuser]
if {$upstream_tuser ne "" && $sof_tuser ne ""} {
    set existing [get_bd_nets -quiet -of_objects $sof_tuser]
    if {$existing ne ""} {
        catch {delete_bd_objs $existing}
    }
    connect_bd_net $upstream_tuser $sof_tuser
    puts "connected pixel_unpack tuser -> sof_gen s_tuser (unused, kept out of dangling)"
}

validate_bd_design
save_bd_design

set dangling {}
foreach p [get_bd_pins -of_objects $sof] {
    if {[get_property DIR $p] ne "I"} { continue }
    if {[get_bd_nets -quiet -of_objects $p] eq ""} {
        lappend dangling [get_property NAME $p]
    }
}
if {[llength $dangling] > 0} {
    puts "STILL DANGLING: $dangling"
    exit 1
}
puts "check: every input of /sof_gen_0 is driven"

reset_target all [get_files -quiet base.bd]
generate_target all [get_files -quiet base.bd] -force
puts "RESULT: SOF WIRING FINALISED"
exit 0
