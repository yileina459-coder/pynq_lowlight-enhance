#!/bin/sh
# One-shot status for the HDMI demo on the board.
#
# Why this exists: querying the board over ssh with anything more complex than a single word kept
# breaking - nested $(...), redirections and quotes get mangled on the way through PowerShell, and a
# mangled '<' leaves a process waiting on stdin so the call hangs instead of failing. Every question
# worth asking is answered here instead, so the caller only ever runs:
#
#   sh /home/xilinx/status.sh
#
# It prints the process count, how long the demo has been up, what is on screen, how playback is doing
# and where the logs are.

echo "=== processes ==="
ps -eo pid,etime,args= | grep '[h]dmi_resident' | sed 's/ *$//'
echo "count: $(ps -eo args= | grep -c '[h]dmi_resident')"

echo
echo "=== state (/tmp/hdmi_state.txt) ==="
cat /tmp/hdmi_state.txt 2>/dev/null || echo "(missing)"

echo
echo "=== control files ==="
for f in /tmp/hdmi_image.txt /tmp/hdmi_preset.txt /tmp/hdmi_roll.txt /tmp/hdmi_sof.txt \
         /tmp/hdmi_play.txt /tmp/hdmi_play_fps.txt; do
    if [ -f "$f" ]; then
        printf '  %-28s %s\n' "$f" "$(tr -d '\000' < "$f" | head -c 60)"
    else
        printf '  %-28s (absent)\n' "$f"
    fi
done

echo
echo "=== schedule ==="
if [ -s /tmp/hdmi_play_presets.txt ]; then
    printf '  %s entries, first: %s\n' "$(wc -l < /tmp/hdmi_play_presets.txt)" \
        "$(head -1 /tmp/hdmi_play_presets.txt)"
else
    echo "  (no schedule - playing with the manual preset)"
fi

echo
echo "=== logs ==="
ls -l /tmp/res_*.log 2>/dev/null | sed 's/^/  /'

echo
echo "=== recent preset switches ==="
for log in /tmp/res_*.log; do
    [ -s "$log" ] || continue
    hits=$(tr -d '\000' < "$log" | awk '/preset ->/' | tail -n 6)
    if [ -n "$hits" ]; then
        echo "  from $log:"
        echo "$hits" | sed 's/^/    /'
    fi
done

echo
echo "=== writing-side status (VDMA) ==="
for log in /tmp/res_*.log; do
    [ -s "$log" ] || continue
    printf '  %s: writeframe failures=%s, hitches=%s\n' "$log" \
        "$(tr -d '\000' < "$log" | awk '/writeframe failed/' | wc -l)" \
        "$(tr -d '\000' < "$log" | awk '/behind by/' | wc -l)"
done
