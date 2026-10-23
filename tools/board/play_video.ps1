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

.PARAMETER Auto
    'clip' or 'adaptive'. Empty (the default) keeps the single -Preset for the whole sequence.
    'clip' analyses the clip and uses the preset with the best mean legibility - the right answer when
    the ask is "make the whole video reasonably clear". 'adaptive' produces a per-frame schedule with
    hysteresis, a minimum segment length and boundary snapping; the board applies it while playing by
    rewriting the configuration, which does not interrupt the stream. In both cases -Preset is ignored.

.EXAMPLE
    tools\board\play_video.ps1 -Video C:\Users\79171\Desktop\clip.mp4

.EXAMPLE
    tools\board\play_video.ps1 -Video clip.mp4 -Fps 24 -Seconds 10 -Preset clarity

.EXAMPLE
    tools\board\play_video.ps1 -Video clip.mp4 -Auto clip
    tools\board\play_video.ps1 -Video clip.mp4 -Auto adaptive
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Video,
    [double]$Fps = 30,
    [double]$Seconds = 6,
    [string]$Preset = 'clarity',
    [int]$Roll = 0,
    # Analyse the clip first and let the analysis choose the preset. 'clip' picks one preset for the
    # whole sequence (perfectly steady); 'adaptive' allows a handful of switches, placed on the actual
    # scene cuts and subject to a minimum segment length, so the picture never flutters.
    [ValidateSet('', 'clip', 'adaptive')][string]$Auto = '',
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
    # Truncate rather than delete: /tmp is sticky, so a non-root user cannot remove a file root
# created, and "rm -f" failing silently is why stopping playback never worked.
$null = Invoke-Board ": > /tmp/hdmi_play.txt; : > /tmp/hdmi_play_presets.txt"
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
# --- 1b) let the analysis choose the preset ----------------------------------------------
$scheduleFile = Join-Path $repo '.tmp\clip_analysis\schedule.txt'
if ($Auto) {
    $analysisDir = Join-Path $repo '.tmp\clip_analysis'
    Write-Host "analysing the clip (-Auto $Auto) - this evaluates every candidate on every frame" -ForegroundColor Cyan
    & $python (Join-Path $repo 'tools\analyze_video.py') $localFrames --outdir $analysisDir --mode $Auto --fps $Fps
    if ($LASTEXITCODE -ne 0) { throw "clip analysis failed" }
    $Preset = (& $python -c "import json,sys; d=json.load(open(r'$analysisDir\analysis.json',encoding='utf-8')); print(d['segments'][0]['preset'] if d['mode']=='clip' else d['clip_best'])").Trim()
    Write-Host "preset chosen by the analysis: $Preset" -ForegroundColor Green
} else {
    if (Test-Path $scheduleFile) { Remove-Item $scheduleFile -Force }
}

Write-Host ("packing {0} frames ({1:N0} MB)" -f $frames.Count,
            (($frames | Measure-Object Length -Sum).Sum / 1MB)) -ForegroundColor Cyan

# --- 2) one archive, one copy ------------------------------------------------------------
$archive = Join-Path $repo '.tmp\frames.tar'
if (Test-Path $archive) { Remove-Item $archive -Force }
& tar -cf $archive -C $localFrames .
& scp -o StrictHostKeyChecking=no -o ConnectTimeout=20 $archive "${board}:/tmp/frames.tar" 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) { throw "copy failed - is the board reachable at 192.168.2.99?" }

if ($Auto -and (Test-Path $scheduleFile)) {
    & scp -o StrictHostKeyChecking=no -o ConnectTimeout=20 $scheduleFile "${board}:/tmp/hdmi_uploads/play_presets.txt" 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "could not copy the preset schedule to the board" }
    Write-Host "preset schedule copied ($((Get-Content $scheduleFile).Count) entries)" -ForegroundColor Cyan
}
$null = Invoke-Board "rm -rf $remoteDir && mkdir -p $remoteDir && tar -xf /tmp/frames.tar -C $remoteDir && rm -f /tmp/frames.tar && ls $remoteDir | wc -l"
$count = (Invoke-Board "ls $remoteDir | wc -l").Trim()
Write-Host "board now holds $count frame(s) in $remoteDir" -ForegroundColor Cyan

# --- 3) ask the running demo to play them -------------------------------------------------
$scheduleArg = if ($Auto) { 'cp /tmp/hdmi_uploads/play_presets.txt /tmp/hdmi_play_presets.txt' } else { ': > /tmp/hdmi_play_presets.txt' }
$null = Invoke-Board "echo $Fps > /tmp/hdmi_play_fps.txt; echo $Preset > /tmp/hdmi_preset.txt; echo $Roll > /tmp/hdmi_roll.txt; $scheduleArg; echo $remoteDir > /tmp/hdmi_play.txt"
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
