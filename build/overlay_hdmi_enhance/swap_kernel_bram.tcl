# -----------------------------------------------------------------------------
# Swap the port-configured enhance kernel for the memory-configured one.
#
#   vivado -mode batch -source build\overlay_hdmi_enhance\swap_kernel_bram.tcl
#
# What changes and why
#   enhance_stream      takes nine configuration values on plain ports. HLS registers them in
#                       the pipeline prologue, and a free-running kernel runs that prologue
#                       once - so a preset change required a kernel reset, which interrupted
#                       the pixel stream and made the video-output core underflow.
#   enhance_stream_cfg  reads one 64-bit word from a BRAM port on every pixel. The address
#                       depends on runtime data, so HLS cannot fold the read away and the
#                       value stays live: software writes the GPIO pair and the next pixel
#                       already uses the new preset.
#
#   The reset bridge stays in the design but is never pulsed any more. The configuration
#   splitter (enh_cfg_split) is no longer needed because the kernel unpacks the word itself.
#
# The memory is src/rtl/cfg_bram/cfg_bram.v - two 64-bit words, true dual port, written from
# the 100 MHz PS domain and read from the kernel's 142.857 MHz clock.
#
# On adding the IP: `update_ip_catalog -add_ip` refused the archive twice with "the specified
# repository is not an existing IP repository in the project", even after adding the path to
# IP_REPO_PATHS. Extracting the archive into a directory that is already a repository path and
# rebuilding the catalog is what works.
# -----------------------------------------------------------------------------

set script_dir [file dirname [file normalize [info script]]]
set repo_root  [file normalize [file join $script_dir ".." ".."]]
set proj_file  [file join $script_dir ".work" "tree" "boards" "Pynq-Z2" "base" "base" "base.xpr"]

open_project $proj_file

# 1) The new kernel's IP, already extracted into a repository the project knows about.
set ip_repo [file join $script_dir ".work" "enhance_ip_cfg"]
if {![file exists [file join $ip_repo "component.xml"]]} {
    puts "ERROR: $ip_repo is not an extracted IP repository"
    exit 1
}
set existing [get_property IP_REPO_PATHS [current_project]]
if {[lsearch -exact $existing $ip_repo] < 0} {
    set_property IP_REPO_PATHS [concat $existing $ip_repo] [current_project]
}
update_ip_catalog -rebuild
puts "ip catalog rebuilt"

# 2) The configuration memory as a module reference.
set rtl [file join $repo_root "src" "rtl" "cfg_bram" "cfg_bram.v"]
if {[llength [get_files -quiet $rtl]] == 0} {
    add_files -norecurse -fileset sources_1 $rtl
    puts "added $rtl"
}
update_compile_order -fileset sources_1

# 3) Remove the old kernel and the now-unused splitter.
set old_cell [get_bd_cells -quiet enhance_0]
if {$old_cell eq ""} {
    puts "NOTE: enhance_0 already replaced"
} else {
    delete_bd_objs [get_bd_cells $old_cell]
    puts "deleted enhance_0"
}
set splitter [get_bd_cells -quiet enh_cfg_split_0]
if {$splitter ne ""} {
    delete_bd_objs [get_bd_cells $splitter]
    puts "deleted enh_cfg_split_0"
}

puts "RESULT: OLD CELLS REMOVED"
exit 0
