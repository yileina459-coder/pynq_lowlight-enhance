#!/bin/sh
# Put the board back into one clean, predictable state.
#
# Why this exists
#   Testing leaves a trail: a playback clip looping, a preset schedule for a video that no longer
#   matters, a stray test picture. The screen then shows a mixture of everything that was ever loaded,
#   which is confusing to look at and useless as a demo. One command should clear it:
#
#       echo xilinx | sudo -S sh /home/xilinx/reset_board.sh [image] [preset]
#
#   Defaults: testcard_640x480.png with the clarity preset. The file must already exist in this
#   directory or in /tmp/hdmi_uploads.

set -u

echo "running as: $(id)"
echo "file: $(ls -l /tmp/hdmi_play_presets.txt 2>&1 | head -1)"

IMAGE=${1:-testcard_640x480.png}
PRESET=${2:-clarity}
DIR=/home/xilinx/jupyter_notebooks/hdmi_enh2

echo "=== stopping playback ==="
# Truncate, do not delete: /tmp is sticky, so a non-root user cannot remove a file root created.
truncate -s 0 /tmp/hdmi_play.txt 2>/dev/null || true
truncate -s 0 /tmp/hdmi_play_presets.txt 2>/dev/null || true
truncate -s 0 /tmp/hdmi_play_fps.txt 2>/dev/null || true
sleep 2

echo "=== clearing the uploaded clip frames ==="
rm -rf /tmp/hdmi_uploads/clip 2>/dev/null || true
rm -f /tmp/hdmi_uploads/play_presets.txt 2>/dev/null || true
remaining=$(ls /tmp/hdmi_uploads 2>/dev/null | wc -l)
echo "  /tmp/hdmi_uploads still holds $remaining file(s) (pictures you uploaded)"

echo "=== choosing the picture and preset ==="
if [ -f "$DIR/$IMAGE" ]; then
    echo "$IMAGE" > /tmp/hdmi_image.txt
    echo "  image -> $IMAGE"
elif [ -f "/tmp/hdmi_uploads/$IMAGE" ]; then
    echo "/tmp/hdmi_uploads/$IMAGE" > /tmp/hdmi_image.txt
    echo "  image -> /tmp/hdmi_uploads/$IMAGE"
else
    echo "  WARNING: $IMAGE not found; leaving the current picture alone"
fi
echo "$PRESET" > /tmp/hdmi_preset.txt
echo "0" > /tmp/hdmi_roll.txt
echo "1" > /tmp/hdmi_sof.txt
echo "  preset -> $PRESET, roll 0, SOF on"

sleep 3
echo
echo "=== state now ==="
cat /tmp/hdmi_state.txt 2>/dev/null || echo "(the resident demo is not running)"
