# Step B: wire the memory-configured kernel and its configuration memory.
#
#   vivado -mode batch -source build\overlay_hdmi_enhance\swap_kernel_b.tcl
#
# Pin names are read from the design rather than guessed - step A printed them, and the
# stream interface of this IP exposes individual pins (s_in_TDATA ...) instead of the
# s_axis_* names the previous kernel used.
#
# Clock domains:
#   ap_clk / cfg_bram.aclk   142.857 MHz pixel clock (ps7_0/FCLK_CLK1)
#   cfg_bram.pclk            100 MHz PS AXI clock (ps7_0/FCLK_CLK0), same as the GPIO
# The memory is a true dual-port BRAM, so those two clocks stay independent; a write is
# atomic per word, which is why the reader can never see half a configuration.

set script_dir [file dirname [file normalize [info script]]]
set proj_file  [file join $script_dir ".work" "tree" "boards" "Pynq-Z2" "base" "base" "base.xpr"]

open_project $proj_file
open_bd_design [get_files -quiet base.bd]

set kernel [get_bd_cells /enhance_cfg_0]
set bridge [get_bd_cells /enh_rst_bridge_0]
set stamp_in  [get_bd_cells -quiet /stamp_in_0]
set stamp_out [get_bd_cells -quiet /stamp_out_0]
puts "stamp_in_0: [llength $stamp_in]  stamp_out_0: [llength $stamp_out]"

# --- clock and reset ---------------------------------------------------------
connect_bd_net [get_bd_pins ps7_0/FCLK_CLK1] [get_bd_pins $kernel/ap_clk]
connect_bd_net [get_bd_pins $bridge/ap_rst_n] [get_bd_pins $kernel/ap_rst_n]
puts "connected ap_clk and ap_rst_n"

# --- AXI4-Stream in and out, pin by pin -------------------------------------
set suffixes {tdata tvalid tready tkeep tstrb tuser tlast tid tdest}
if {$stamp_in ne ""} {
    foreach suffix $suffixes {
        set src [get_bd_pins -quiet $stamp_in/m_axis_$suffix]
        set dst [get_bd_pins -quiet $kernel/s_in_$suffix]
        if {$src ne "" && $dst ne ""} {
            connect_bd_net $src $dst
        }
    }
    puts "wired stamp_in_0 -> kernel"
}
if {$stamp_out ne ""} {
    foreach suffix $suffixes {
        set src [get_bd_pins -quiet $kernel/s_out_$suffix]
        set dst [get_bd_pins -quiet $stamp_out/s_axis_$suffix]
        if {$src ne "" && $dst ne ""} {
            connect_bd_net $src $dst
        }
    }
    puts "wired kernel -> stamp_out_0"
}

# --- configuration memory ----------------------------------------------------
if {[llength [get_bd_cells -quiet /cfg_bram_0]] == 0} {
    create_bd_cell -type module -reference cfg_bram /cfg_bram_0
    puts "created /cfg_bram_0"
}
set mem [get_bd_cells /cfg_bram_0]

connect_bd_net [get_bd_pins ps7_0/FCLK_CLK1] [get_bd_pins $mem/aclk]
connect_bd_net [get_bd_pins ps7_0/FCLK_CLK0] [get_bd_pins $mem/pclk]

connect_bd_net [get_bd_pins $kernel/cfg_EN_A]     [get_bd_pins $mem/en_a]
connect_bd_net [get_bd_pins $kernel/cfg_Addr_A]   [get_bd_pins $mem/addr_a]
connect_bd_net [get_bd_pins $mem/dout_a]          [get_bd_pins $kernel/cfg_Dout_A]
puts "wired configuration memory to the kernel"

# The GPIO pair still carries the 64-bit word: channel 1 = word 0, channel 2 = word 1.
set gpio [get_bd_cells /gpio_enh_cfg]
foreach pin [get_bd_pins -of_objects $gpio] {
    set name [get_property NAME $pin]
    if {[get_property DIR $pin] eq "O"} {
        puts "gpio output pin available: $name"
    }
}
set lo [get_bd_pins -quiet $gpio/gpio_io_o]
set hi [get_bd_pins -quiet $gpio/gpio2_io_o]
if {$lo eq "" || $hi eq ""} {
    puts "ERROR: expected gpio_io_o and gpio2_io_o on gpio_enh_cfg"
    exit 1
}
connect_bd_net $lo [get_bd_pins $mem/cfg_lo]
connect_bd_net $hi [get_bd_pins $mem/cfg_hi]
puts "wired gpio_enh_cfg -> configuration memory"

validate_bd_design
save_bd_design
puts "RESULT: KERNEL SWAPPED"
exit 0
