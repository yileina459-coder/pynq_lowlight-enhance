# Step A: replace the kernel cell and report the new cell's pins.
#
#   vivado -mode batch -source build\overlay_hdmi_enhance\swap_kernel_a.tcl
#
# The pattern matters: `get_bd_cells -quiet enhance_0` matches nothing, while `/enhance_0`
# (or a -hierarchical -filter query) does. An earlier revision of this script used the bare
# name, concluded the cell was already gone, and silently did nothing.
#
# This step only deletes and creates; wiring is a separate script so the pin names can be
# read from a run instead of guessed.

set script_dir [file dirname [file normalize [info script]]]
set repo_root  [file normalize [file join $script_dir ".." ".."]]
set proj_file  [file join $script_dir ".work" "tree" "boards" "Pynq-Z2" "base" "base" "base.xpr"]

open_project $proj_file
open_bd_design [get_files -quiet base.bd]

# Make sure the new kernel's IP is in the catalog.
set ip_repo [file join $script_dir ".work" "enhance_ip_cfg"]
set existing [get_property IP_REPO_PATHS [current_project]]
if {[lsearch -exact $existing $ip_repo] < 0} {
    set_property IP_REPO_PATHS [concat $existing $ip_repo] [current_project]
    update_ip_catalog -rebuild
}

# The configuration memory, as a module reference.
set rtl [file join $repo_root "src" "rtl" "cfg_bram" "cfg_bram.v"]
if {[llength [get_files -quiet $rtl]] == 0} {
    add_files -norecurse -fileset sources_1 $rtl
}
update_compile_order -fileset sources_1

# Remove the old kernel and the splitter it no longer needs.
foreach cell {/enhance_0 /enh_cfg_split_0} {
    if {[llength [get_bd_cells -quiet $cell]] > 0} {
        delete_bd_objs [get_bd_cells $cell]
        puts "deleted $cell"
    } else {
        puts "not present: $cell"
    }
}

# Create the memory-configured kernel.
if {[llength [get_bd_cells -quiet /enhance_cfg_0]] == 0} {
    create_bd_cell -type ip -vlnv xilinx.com:hls:enhance_stream_cfg:1.0 /enhance_cfg_0
    puts "created /enhance_cfg_0"
}

puts "--- pins of /enhance_cfg_0 ---"
foreach p [get_bd_pins -of_objects [get_bd_cells /enhance_cfg_0]] {
    puts "PIN [get_property NAME $p] [get_property DIR $p] [get_property LEFT $p]:[get_property RIGHT $p]"
}

puts "--- ports of /cfg_bram_0 (to be created) ---"
# Save: without this the cell exists only in the session, and step B opens the design and
# finds nothing (that is exactly how the first attempt of step B failed).
save_bd_design
puts "RESULT: STEP A DONE"
exit 0
