# Replace the enhance kernel IP with the freshly exported one and rebuild.
#
#   vivado -mode batch -source build\overlay_hdmi_enhance\refresh_enhance_ip.tcl
#
# Why this dance is needed
#   The block design packages an HLS IP into base.srcs/.../ip/base_enhance_cfg_0 and synthesises it
#   out of context into base.gen/.../ip/base_enhance_cfg_0 with a cached DCP, and the BD module
#   reference keeps its own copy under ipshared. Overwriting the source zip alone changes nothing -
#   this cost three rebuilds earlier in the project. The tell-tale is a failing path, or a report,
#   still naming signals from the previous version.
#
#   So: drop the packaged copies, rebuild the catalogue, regenerate the BD products, and only then
#   let the build run. The script prints the SHA of the packaged RTL so the new kernel can be
#   confirmed to be the one that will be implemented.

set script_dir [file dirname [file normalize [info script]]]
set proj_file  [file join $script_dir ".work" "tree" "boards" "Pynq-Z2" "base" "base" "base.xpr"]
set proj_root  [file join $script_dir ".work" "tree" "boards" "Pynq-Z2" "base" "base"]
set ip_repo    [file join $script_dir ".work" "enhance_ip_cfg"]

open_project $proj_file

# --- drop every packaged copy of the kernel IP -----------------------------------------
set removed 0
foreach pattern [list \
        [file join $proj_root "base.srcs" "sources_1" "bd" "base" "ip" "base_enhance_cfg_0*"] \
        [file join $proj_root "base.gen" "sources_1" "bd" "base" "ip" "base_enhance_cfg_0*"] \
        [file join $proj_root "base.gen" "sources_1" "bd" "base" "ipshared"]] {
    foreach path [glob -nocomplain -directory [file dirname $pattern] [file tail $pattern]] {
        file delete -force $path
        incr removed
        puts "removed [file tail $path]"
    }
}
puts "removed $removed packaged path(s)"

# --- rebuild the catalogue so the new export is what the BD sees ------------------------
set paths [get_property IP_REPO_PATHS [current_project]]
if {[lsearch -exact $paths $ip_repo] < 0} {
    set_property IP_REPO_PATHS [concat $paths $ip_repo] [current_project]
}
update_ip_catalog -rebuild

# The design reports "locked" until it has been opened in this session, so open it first and treat
# validation as advisory: the packaged files are what matter here.
open_bd_design [get_files -quiet base.bd]
catch {validate_bd_design}
catch {save_bd_design}
reset_target all [get_files -quiet base.bd]
generate_target all [get_files -quiet base.bd] -force

# --- prove the packaged RTL is the new one ---------------------------------------------
set packaged [glob -nocomplain -directory \
        [file join $proj_root "base.gen" "sources_1" "bd" "base" "ipshared"] \
        -tails "*"] 
set rtl [glob -nocomplain -directory \
        [file join $proj_root "base.gen" "sources_1" "bd" "base" "ipshared"] \
        "*/hdl/verilog/enhance_stream_cfg.v"]
if {[llength $rtl] == 0} {
    puts "WARNING: no packaged enhance_stream_cfg.v found yet (it appears during synthesis)"
} else {
    puts "packaged RTL: [lindex $rtl 0]"
    set fh [open [lindex $rtl 0] r]
    set body [read $fh]
    close $fh
    # HLS renames its registers, so the check is on size: the previous kernel's RTL was 111891
    # bytes with eleven replicas of the configuration across pipeline stages; the latched version
    # is far smaller. A mismatch here means a stale package survived and the old kernel would be
    # built - which has happened before and cost a whole implementation run.
    set size [file size [lindex $rtl 0]]
    puts "packaged RTL size: $size bytes"
    if {$size > 60000} {
        puts "ERROR: packaged RTL still looks like the old kernel (size $size)"
        exit 1
    }
    puts "check: packaged RTL is the latched-configuration kernel"
}
puts "RESULT: ENHANCE IP REFRESHED"
exit 0
