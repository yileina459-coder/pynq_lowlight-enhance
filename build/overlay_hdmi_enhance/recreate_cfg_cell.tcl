# Recreate the cfg_bram cell so its packaged copy matches the current RTL.
#
# Why the earlier attempts failed
#   `create_bd_cell -type module -reference cfg_bram` does not keep a live reference to
#   src/rtl/cfg_bram/cfg_bram.v. It packages the module into an IP core:
#
#       base.srcs/sources_1/bd/base/ip/base_cfg_bram_0_0/base_cfg_bram_0_0.xci
#
#   and synthesises from that package. Editing the source file afterwards changes nothing;
#   two full rebuilds produced the same stale netlist (mem_reg/dout_q, WNS -1.393, 59
#   failing endpoints) even after the source had been rewritten to use xpm_memory_tdpram.
#   Deleting the cell and its package, then creating it again, is what picks up new RTL.
#
# This script: delete cell + package, recreate, rewire, validate, save, regenerate.

set script_dir [file dirname [file normalize [info script]]]
set proj_file  [file join $script_dir ".work" "tree" "boards" "Pynq-Z2" "base" "base" "base.xpr"]
set proj_root  [file join $script_dir ".work" "tree" "boards" "Pynq-Z2" "base" "base"]

open_project $proj_file
open_bd_design [get_files -quiet base.bd]

# --- delete the old cell and its packaged IP ---------------------------------
if {[llength [get_bd_cells -quiet /cfg_bram_0]] > 0} {
    delete_bd_objs [get_bd_cells /cfg_bram_0]
    puts "deleted /cfg_bram_0"
}
save_bd_design
close_bd_design [current_bd_design]

foreach stale [list \
        [file join $proj_root "base.srcs" "sources_1" "bd" "base" "ip" "base_cfg_bram_0_0"] \
        [file join $proj_root "base.gen" "sources_1" "bd" "base" "ip" "base_cfg_bram_0_0"]] {
    if {[file exists $stale]} {
        file delete -force $stale
        puts "removed [file tail $stale]"
    }
}

# --- recreate from the current source ---------------------------------------
open_bd_design [get_files -quiet base.bd]

create_bd_cell -type module -reference cfg_bram /cfg_bram_0
puts "recreated /cfg_bram_0"

set kernel [get_bd_cells /enhance_cfg_0]
set mem    [get_bd_cells /cfg_bram_0]
set gpio   [get_bd_cells /gpio_enh_cfg]

connect_bd_net [get_bd_pins ps7_0/FCLK_CLK1] [get_bd_pins $mem/aclk]
connect_bd_net [get_bd_pins ps7_0/FCLK_CLK0] [get_bd_pins $mem/pclk]
connect_bd_net [get_bd_pins $kernel/cfg_EN_A]  [get_bd_pins $mem/en_a]
connect_bd_net [get_bd_pins $kernel/cfg_Addr_A] [get_bd_pins $mem/addr_a]
connect_bd_net [get_bd_pins $mem/dout_a]        [get_bd_pins $kernel/cfg_Dout_A]
connect_bd_net [get_bd_pins $gpio/gpio_io_o]    [get_bd_pins $mem/cfg_lo]
connect_bd_net [get_bd_pins $gpio/gpio2_io_o]   [get_bd_pins $mem/cfg_hi]
puts "rewired"

validate_bd_design
save_bd_design

reset_target all [get_files -quiet base.bd]
generate_target all [get_files -quiet base.bd] -force
puts "output products regenerated"

# --- verify the packaged copy really carries the new RTL ---------------------
set pkg [file join $proj_root "base.srcs" "sources_1" "bd" "base" "ip" "base_cfg_bram_0_0"]
set found 0
foreach f [glob -nocomplain -directory $pkg -types f *] {
    set fh [open $f r]; set body [read $fh]; close $fh
    if {[string match "*xpm_memory_tdpram*" $body]} { incr found }
}
puts "PACKAGED COPY: $found file(s) mention xpm_memory_tdpram"
if {$found == 0} {
    puts "WARNING: packaged copy may still be stale; check $pkg"
}

puts "RESULT: CFG CELL RECREATED"
exit 0
