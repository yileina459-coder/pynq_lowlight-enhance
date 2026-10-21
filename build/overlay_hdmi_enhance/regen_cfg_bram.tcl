# Force the block design to regenerate the cfg_bram module reference.
#
# Why this is needed
#   A module reference is not read from its source file at synthesis time. Vivado copies the
#   RTL into the BD's generated directory and caches a synthesised checkpoint next to it:
#
#       base.gen/sources_1/bd/base/ip/base_cfg_bram_0_0/synth/base_cfg_bram_0_0.v
#       base.gen/sources_1/bd/base/ip/base_cfg_bram_0_0/base_cfg_bram_0_0.dcp
#
#   Editing src/rtl/cfg_bram/cfg_bram.v therefore had no effect: two rebuilds produced the
#   same stale netlist (mem_reg/dout_q cells, WNS -1.393 with 59 failing endpoints) even
#   though the source had already been rewritten to use xpm_memory_tdpram.
#
#   reset_target + generate_target discards and rebuilds those products.

set script_dir [file dirname [file normalize [info script]]]
set proj_file  [file join $script_dir ".work" "tree" "boards" "Pynq-Z2" "base" "base" "base.xpr"]

open_project $proj_file
open_bd_design [get_files -quiet base.bd]

set bd [get_files -quiet base.bd]
reset_target all $bd
generate_target all $bd -force
puts "regenerated output products for $bd"

save_bd_design
close_project

# Report what the generated copy now contains, so a stale cache cannot slip through again.
set gen [file join $script_dir ".work" "tree" "boards" "Pynq-Z2" "base" "base" "base.gen" "sources_1" "bd" "base" "ip" "base_cfg_bram_0_0" "synth" "base_cfg_bram_0_0.v"]
if {[file exists $gen]} {
    set fh [open $gen r]
    set body [read $fh]
    close $fh
    if {[string match "*xpm_memory_tdpram*" $body]} {
        puts "GENERATED COPY: uses xpm_memory_tdpram (fresh)"
    } else {
        puts "GENERATED COPY: STILL STALE"
        exit 1
    }
} else {
    puts "GENERATED COPY: not found (will be produced by synthesis)"
}

puts "RESULT: BD PRODUCTS REGENERATED"
exit 0
