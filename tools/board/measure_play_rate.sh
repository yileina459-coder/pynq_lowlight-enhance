#!/bin/sh
# Measure the playback rate from the resident's own log.
#
# The per-frame timings say a frame costs about 6 ms, but the loop can still hitch (it used to sleep
# two seconds every fifteen frames). Counting the frame index across a fixed wall-clock interval is the
# only honest measure of the rate the viewer actually sees.

LOG=/tmp/res_fps.log
WINDOW=${1:-10}

last_index() {
    grep -o 'frame *[0-9]*:' "$LOG" | tail -1 | tr -dc '0-9'
}

a=$(last_index)
sleep "$WINDOW"
b=$(last_index)

if [ -z "$a" ] || [ -z "$b" ]; then
    echo "MEASURE FAIL: no frame lines in $LOG yet"
    exit 1
fi

delta=$((b - a))
echo "frames advanced: $delta over ${WINDOW}s -> $(awk "BEGIN{printf \"%.1f\", $delta/$WINDOW}") fps"
echo "requested: $(cat /tmp/hdmi_play_fps.txt 2>/dev/null)"
echo "hitches (behind by): $(grep -c 'behind by' "$LOG")"
echo "schedule switches: $(grep -c 'preset ->' "$LOG")"
echo "last switches:"
grep 'preset ->' "$LOG" | tail -3
