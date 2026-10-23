<#
.SYNOPSIS
    把板子恢复到一个干净的、可预期的状态。

.DESCRIPTION
    测试会在板子上留下痕迹：循环播放的视频、为某段视频生成的挡位排程、随手传上去的测试图。
    屏幕于是变成"所有加载过的东西混在一起"，既不好看也不适合演示。

    这个脚本做四件事：
      1. 停止播放（截断播放文件，不删除——/tmp 有 sticky 位，普通用户删不掉 root 建的文件）；
      2. 清掉上传的视频帧和排程；
      3. 指定一张图片和一个挡位（默认仍是测试卡 + clarity）；
      4. 回读板上状态，确认真的生效。

.PARAMETER Image
    要显示的图片，默认 testcard_640x480.png。必须在板上这两个目录之一：
    /home/xilinx/jupyter_notebooks/hdmi_enh2 或 /tmp/hdmi_uploads。
    用 tools\board\show_image.ps1 上传的图都在后者。

.PARAMETER Preset
    挡位，默认 clarity。

.EXAMPLE
    tools\board\reset_board.ps1

.EXAMPLE
    tools\board\reset_board.ps1 -Image mine_120000_640x480.png -Preset bright
#>
[CmdletBinding()]
param(
    [string]$Image = 'testcard_640x480.png',
    [string]$Preset = 'clarity'
)

# 'Continue', not 'Stop': ssh writes the sudo prompt to stderr, which PowerShell would treat as a
# terminating error even though the command succeeds. play_video.ps1 has the same note.
$ErrorActionPreference = 'Continue'
$repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$board = 'xilinx@192.168.2.99'
$askpass = Join-Path $repo '.tmp\askpass\askpass.bat'
$script = Join-Path $repo 'tools\board\reset_board.sh'

$env:SSH_ASKPASS = $askpass
$env:SSH_ASKPASS_REQUIRE = 'force'
$env:DISPLAY = ':0'

if (-not (Test-Path $askpass)) { throw "missing $askpass (the password helper for ssh)" }

# The remote script is small; ship the current copy each time so a local edit takes effect.
& scp -o StrictHostKeyChecking=no -o ConnectTimeout=20 $script "${board}:/home/xilinx/" 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) { throw "cannot copy the reset script - is the board reachable at 192.168.2.99?" }

$output = & ssh -o StrictHostKeyChecking=no -o LogLevel=ERROR -o ConnectTimeout=20 $board `
    "echo xilinx | sudo -S sh /home/xilinx/reset_board.sh '$Image' '$Preset'" 2>$null
($output | Out-String) | ForEach-Object { Write-Host $_ }

# Verify from the board's own state file rather than trusting the script's echo.
$state = (& ssh -o StrictHostKeyChecking=no -o LogLevel=ERROR -o ConnectTimeout=20 $board `
    'cat /tmp/hdmi_state.txt' 2>$null | Out-String)
if ($state -match 'playing=\d+') {
    Write-Warning 'the board still reports a clip playing - the playback file may be locked'
    exit 1
}
if ($state -match "preset=$Preset") {
    Write-Host "OK - the board is showing $Image with preset $Preset" -ForegroundColor Green
    exit 0
}
Write-Warning "the board's state does not confirm preset=$Preset yet:"
$state | ForEach-Object { Write-Host "  $_" }
exit 2
