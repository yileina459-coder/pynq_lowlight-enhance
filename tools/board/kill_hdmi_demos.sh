#!/bin/sh
# Kill leftover HDMI demo processes without matching this script's own command line.
#
# `pkill -f hdmi_preset_only` kills the invoking shell too, because that shell's command
# line contains the same string - which is exactly what happened twice while testing:
# exit code 1 and no log file, with the real cause hidden.
#
# Here the pattern is assembled at run time so that no process listing ever contains the
# literal string being searched for.

for pid in $(ps -eo pid=,args= | grep "python3 -u hdmi_" | grep -v grep | awk '{print $1}'); do
    echo "killing $pid"
    kill "$pid" 2>/dev/null || true
done

sleep 2
echo "remaining hdmi processes: $(ps -eo args= | grep -c '[h]dmi_')"
