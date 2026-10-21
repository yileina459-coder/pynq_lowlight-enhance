#!/bin/sh
# Kill leftover HDMI demo processes without matching this script or the invoking shell.
#
# Three different traps have bitten here:
#   1. `pkill -f hdmi_preset_only` also matches the shell that runs it, because that shell's
#      command line contains the same string - the session dies and the redirect never runs,
#      so the failure looks like "the script crashed with no log".
#   2. `grep "python3 -u hdmi_"` matches the shell wrapping the run for the same reason.
#   3. Even with a bracket trick in the pattern, the bracket form appears in the calling
#      command line and can match itself.
#
# So: match on the argument vector of real python processes only. The awk program compares
# argv[1] (the interpreter) and argv[3] (the script name) instead of pattern-matching the
# whole command line, which cannot match awk itself or the shell around it.

ps -eo pid=,args= | awk '
{
    pid = $1
    # argv[1] is the interpreter, argv[2] is "-u", argv[3] is the script
    if ($2 ~ /python3$/ && $3 == "-u" && $4 ~ /^hdmi_/) {
        print pid
    }
}' | while read -r pid; do
    echo "killing $pid"
    kill "$pid" 2>/dev/null || true
done

sleep 2
count=$(ps -eo args= | awk '$1 ~ /python3$/ && $2 == "-u" && $3 ~ /^hdmi_/' | wc -l)
echo "remaining hdmi demo processes: $count"
