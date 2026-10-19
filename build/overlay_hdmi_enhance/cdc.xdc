# -----------------------------------------------------------------------------
# CDC constraints for the enhance HDMI overlay.
#
# Why these are false paths, not real ones
#   The configuration GPIO lives on clk_fpga_0 (100 MHz, PS AXI-Lite) and drives
#   the kernel's 59 config bits, which are sampled on clk_fpga_1 (142.86 MHz, the
#   pixel-clock domain). Vivado treats the two PS clocks as related and times the
#   path as synchronous, which failed:
#       Slack (VIOLATED) -1.333ns  from gpio_enh_cfg/.../gpio_Data_Out_reg
#                                  to   enhance_0/inst/zext_..._reg
#   It cannot be fixed by placement (the requirement is 1 ns across two clocks)
#   and it does not need to be: the configuration is written once and then left
#   alone for millions of cycles. While software changes a preset the kernel may
#   see a mix of old and new parameter values for at most one frame; the next
#   frame is already correct. That is acceptable for a user-facing preset switch.
#
#   The same applies in reverse to the two latency stamps: they are cycle values
#   that change at most once per PL configuration, so a torn read is impossible in
#   practice and harmless if it happened.
#
# What is NOT relaxed here
#   The pixel stream itself (AXI4-Stream) stays fully timed; only the static
#   configuration and status buses are excluded.
#
# NOTE: this file must contain nothing but constraint commands. An earlier version
# used set/puts/if, which XDC does not support - Vivado reported
#   CRITICAL WARNING: [Designutils 20-1307] Command 'puts' is not supported ...
# and silently applied no constraint at all.
# -----------------------------------------------------------------------------

set_false_path -from [get_cells -hier -filter {NAME =~ "*gpio_enh_cfg*"}] -to [get_cells -hier -filter {NAME =~ "*enhance_0*"}]

set_false_path -from [get_cells -hier -filter {NAME =~ "*stamp_in_0*"}]  -to [get_cells -hier -filter {NAME =~ "*gpio_enh_lat*"}]
set_false_path -from [get_cells -hier -filter {NAME =~ "*stamp_out_0*"}] -to [get_cells -hier -filter {NAME =~ "*gpio_enh_lat*"}]
