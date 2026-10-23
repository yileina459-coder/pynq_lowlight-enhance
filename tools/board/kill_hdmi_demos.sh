#!/bin/sh
# Stop every demo process on the board and verify it.
#
# Two traps made this script unreliable before:
#   1. matching on the command line also matched the shell that ran the script, so the session
#      died and the failure looked like "the script crashed with no output";
#   2. `kill` as the login user silently fails against processes started through sudo, so the
#      script printed "killing <pid>" while the demo kept running.
#
# And a third, found the hard way: the pattern list did not contain hdmi_resident, so the resident
# demo - the one process that owns the VDMA - was never stopped. Two residents then ran at once,
# the MM2S channel halted, and hours went into diagnosing a "hardware defect" that was contention.
# Every demo entry point must be listed here, and the script now fails loudly if anything survives.
#
# Run it as root:   echo xilinx | sudo -S sh /home/xilinx/kill_hdmi_demos.sh

if [ "$(id -u)" != "0" ]; then
    echo "warning: not running as root - demo processes started via sudo will survive"
fi

for pattern in hdmi_resident hdmi_player hdmi_show_image hdmi_tour hdmi_preset_only \
               hdmi_ruler hdmi_stock_640 hdmi_live_check hdmi_vdma_demo hdmi_solid \
               hdmi_static_frame hdmi_smooth_demo hdmi_restore_hpd hdmi_out_probe; do
    pkill -9 -f "$pattern" 2>/dev/null
done

sleep 2

count=$(ps -eo args= | awk '$1 ~ /python3$/ && $2 == "-u" && $3 ~ /^hdmi_/' | wc -l)
echo "remaining hdmi demo processes: $count"
if [ "$count" != "0" ]; then
    ps -eo pid=,user=,args= | awk '$0 ~ /python3/ && $0 ~ /hdmi_/ && $0 !~ /awk/ {
        print "  still running: pid", $1, "user", $2
    }'
    echo "FAILED: something is still driving the video hardware"
    exit 1
fi

echo "all hdmi demo processes stopped"
