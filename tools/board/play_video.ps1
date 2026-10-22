<#
.SYNOPSIS
    Play a video file on the board, processed by the FPGA, without restarting the demo.

.DESCRIPTION
    Three steps, all automatic:
      1. decode the video on this PC into numbered 640x480 frames (tools/make_video_frames.py);
      2. copy the whole sequence to the board as one archive (a few hundred scp calls would be slow);
      3. point the running demo at the sequence, so it plays frames through the kernel in a loop.

    Step 3 matters: the demo process owns the VDMA, and stopping it to start a separate player
    interrupts the pixel stream - this capture dongle then shows colour bars until the cable is
    replugged or the board rebooted. The demo therefore gained a playback mode that is switched by
    a file (/tmp/hdmi_play.txt), which is why this script never restarts anything.

.PARAMETER Fps
    Playback rate. The measured cost of feeding one frame from the PS is about 15.6 ms (~63 fps),
    so 30 fps has comfortable margin and 60 fps very little.

.PARAMETER Seconds
    How much of the video to take. Every frame costs about 0.9 MB of board DDR, so the default six
    seconds keeps the sequence near 166 MB at 30 fps.

.EXAMPLE
    tools\board\play_video.ps1 -Video C:\Users\79171\Desktop\clip.mp4

.EXAMPLE
    tools\board\play_video.ps1 -Video clip.mp4 -Fps 24 -Seconds 10 -Preset clarity
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Video,
    [double]$Fps = 30,
    [double]$Seconds = 6,
    [string]$Preset = 'clarity',
    [int]$Roll = 0,
    [switch]$Stop
)

# 'Continue', not 'Stop': the board's clock drifts from this PC's, and tar reports "time stamp is
# ... s in the future" on stderr for every frame. With 'Stop' that harmless warning aborts the run.
$ErrorActionPreference = 'Continue'
$repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$python = 'C:\Users\79171\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe'
$board = 'xilinx@192.168.2.99'
$askpass = Join-Path $repo '.tmp\askpass\askpass.bat'
$remoteDir = '/tmp/hdmi_uploads/clip'

$env:SSH_ASKPASS = $askpass
$env:SSH_ASKPASS_REQUIRE = 'force'
$env:DISPLAY = ':0'

function Invoke-Board {
    # Out-String keeps the result a string even when the remote command prints nothing: a null
    # return here looked exactly like "the demo is not running", which was a false alarm.
    param([string]$Command)
    $output = & ssh -o StrictHostKeyChecking=no -o LogLevel=ERROR -o ConnectTimeout=20 $board $Command 2>$null
    return ($output | Out-String)
}

if ($Stop) {
    $null = Invoke-Board "rm -f /tmp/hdmi_play.txt"
    Start-Sleep -Seconds 2
    Write-Host "playback stopped; the demo is back to the still picture" -ForegroundColor Green
    Invoke-Board "cat /tmp/hdmi_state.txt" | ForEach-Object { Write-Host "  $_" }
    exit 0
}

if (-not (Test-Path $Video)) { throw "no such video: $Video" }
if (-not (Test-Path $python)) { throw "bundled python not found: $python" }

# --- 1) decode here ---------------------------------------------------------------------
$localFrames = Join-Path $repo '.tmp\frames'
& $python (Join-Path $repo 'tools\make_video_frames.py') $Video --out $localFrames --fps $Fps --seconds $Seconds
if ($LASTEXITCODE -ne 0) { throw "frame extraction failed" }

$frames = Get-ChildItem $localFrames -Filter 'frame_*.png'
if ($frames.Count -eq 0) { throw "no frames produced" }
Write-Host ("packing {0} frames ({1:N0} MB)" -f $frames.Count,
            (($frames | Measure-Object Length -Sum).Sum / 1MB)) -ForegroundColor Cyan

# --- 2) one archive, one copy ------------------------------------------------------------
$archive = Join-Path $repo '.tmp\frames.tar'
if (Test-Path $archive) { Remove-Item $archive -Force }
& tar -cf $archive -C $localFrames .
& scp -o StrictHostKeyChecking=no -o ConnectTimeout=20 $archive "${board}:/tmp/frames.tar" 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) { throw "copy failed - is the board reachable at 192.168.2.99?" }

$null = Invoke-Board "rm -rf $remoteDir && mkdir -p $remoteDir && tar -xf /tmp/frames.tar -C $remoteDir && rm -f /tmp/frames.tar && ls $remoteDir | wc -l"
$count = (Invoke-Board "ls $remoteDir | wc -l").Trim()
Write-Host "board now holds $count frame(s) in $remoteDir" -ForegroundColor Cyan

# --- 3) ask the running demo to play them -------------------------------------------------
$null = Invoke-Board "echo $Fps > /tmp/hdmi_play_fps.txt; echo $Preset > /tmp/hdmi_preset.txt; echo $Roll > /tmp/hdmi_roll.txt; echo $remoteDir > /tmp/hdmi_play.txt"
Start-Sleep -Seconds 3

$state = Invoke-Board "cat /tmp/hdmi_state.txt"
$running = Invoke-Board "ps -eo args= | grep -c '[h]dmi_resident'"
if (-not $running -or $running.Trim() -eq '0') {
    Write-Warning "the resident demo is not running, so there is nothing to play through."
    Write-Host "Start it once, then run this script again (it never restarts the process)." -ForegroundColor Yellow
    exit 1
}

if ($state -match 'playing=\d+ frames') {
    Write-Host "playing" -ForegroundColor Green
    $state | ForEach-Object { Write-Host "  $_" }
} else {
    Write-Warning "the demo has not picked the sequence up yet:"
    $state | ForEach-Object { Write-Host "  $_" }
}

Write-Host ""
Write-Host "stop with:  tools\board\play_video.ps1 -Video x -Stop" -ForegroundColor Gray
