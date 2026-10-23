#!/bin/sh
# Print the scheduled preset switches from the resident's log.
#
# Why a separate file: the log carries a few control bytes from the bitstream banner, and this board's
# busybox grep -a hangs on it - it never returns, even on a 400 KB file. Stripping NULs first and then
# filtering with awk both avoids that and keeps the output readable.
#
#   sh /home/xilinx/show_switches.sh [count]
#
# Each line looks like:   preset -> night (scheduled, frame 0)
# The frame number is the position within the clip, so the sequence shows exactly where the analyser
# asked for a change.

LOG=${LOG:-/tmp/res_fps.log}
COUNT=${1:-10}

tr -d '\000' < "$LOG" | awk '/preset ->/' | tail -n "$COUNT"
