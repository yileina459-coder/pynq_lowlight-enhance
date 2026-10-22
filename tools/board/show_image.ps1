<#
.SYNOPSIS
    Show your own picture on the board's HDMI output.

.DESCRIPTION
    One command, from any picture on this PC to the panel:
      1. convert it to the 640x480 PNG the output expects (letterbox / crop / stretch),
      2. copy it to /tmp/hdmi_uploads on the board,
      3. point the resident demo at it,
      4. read the board's own state file back, so "it worked" is verified rather than assumed.

    No sudo anywhere: the demo directory is root owned, but /tmp is world writable and the resident
    demo reads whatever path it is given, so uploaded pictures live in /tmp/hdmi_uploads and the
    control files in /tmp/hdmi_*.txt are mode 666.

    The demo process owns the VDMA, so it must already be running and must not be restarted -
    restarting interrupts the pixel stream, and this capture dongle does not re-lock without a
    physical cable replug. Hence the file-based switch.

.PARAMETER Fit
    letterbox (default) keeps the aspect ratio and pads with -Background.
    crop fills the frame and cuts the overflow.
    stretch fills the frame and distorts.

.EXAMPLE
    tools\board\show_image.ps1 -Image C:\Users\79171\Desktop\photo.jpg

.EXAMPLE
    tools\board\show_image.ps1 -Image photo.jpg -Fit crop -Preset threshold
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Image,
    [ValidateSet('letterbox', 'crop', 'stretch')][string]$Fit = 'letterbox',
    [int]$Background = 0,
    [string]$Preset = '',
    # Apply the brightness curve here, on the PC, instead of on the board. The hardware gain path
    # produces column striping in the current bitstream (see docs/hdmi_status.md), so this is the
    # route that gives a clean bright picture today; the board then only adds local contrast.
    [ValidateSet('', 'bright', 'night', 'document', 'reading')][string]$Tone = '',
    [switch]$KeepLocal
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$python = 'C:\Users\79171\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe'
$board = 'xilinx@192.168.2.99'
$uploadDir = '/tmp/hdmi_uploads'
$askpass = Join-Path $repo '.tmp\askpass\askpass.bat'

if (-not (Test-Path $python)) { throw "bundled python not found: $python" }
if (-not (Test-Path $askpass)) { throw "ssh helper missing: $askpass" }
if (-not (Test-Path $Image)) { throw "no such picture: $Image" }

$env:SSH_ASKPASS = $askpass
$env:SSH_ASKPASS_REQUIRE = 'force'
$env:DISPLAY = ':0'

function Invoke-Board {
    param([string]$Command)
    $out = & ssh -o StrictHostKeyChecking=no -o ConnectTimeout=20 $board $Command 2>$null
    return $out
}

# --- 1) convert -------------------------------------------------------------------------
$stamp = Get-Date -Format 'HHmmss'
$name = "mine_${stamp}_640x480.png"
$local = Join-Path $repo ".tmp\upload\$name"
$prepareArgs = @((Join-Path $repo 'tools\prepare_image.py'), $Image, '--out', $local,
                 '--fit', $Fit, '--background', $Background)
if ($Tone) { $prepareArgs += @('--tone', $Tone) }
& $python @prepareArgs
if ($LASTEXITCODE -ne 0) { throw "conversion failed" }

# --- 2) copy to the board ---------------------------------------------------------------
& scp -o StrictHostKeyChecking=no -o ConnectTimeout=20 $local "${board}:${uploadDir}/" 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    # The directory may not exist after a reboot; create it and retry once.
    $null = Invoke-Board "mkdir -p $uploadDir"
    & scp -o StrictHostKeyChecking=no -o ConnectTimeout=20 $local "${board}:${uploadDir}/" 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "scp failed - is the board reachable at 192.168.2.99?" }
}

# --- 3) switch the picture --------------------------------------------------------------
$null = Invoke-Board "echo $uploadDir/$name > /tmp/hdmi_image.txt"

$chosenPreset = $Preset
if ($Tone) {
    # The brightness curve already happened on the PC, so the board only has to sharpen. 'clarity'
    # is local contrast with unity gain, which is the part of the kernel that is verified clean;
    # the gain path currently stripes (see docs/hdmi_status.md).
    $chosenPreset = if ($Preset -in @('', 'auto')) { 'clarity' } else { $Preset }
    Write-Host "brightened on the PC (tone=$Tone); board preset '$chosenPreset'" -ForegroundColor Cyan
}
elseif ($Preset -eq 'auto') {
    # Let the simulator look at the converted picture and pick the tone curve that suits it.
    # Same code path as tools\preview_enhance.py, so the preview and the board agree.
    $advice = & $python (Join-Path $repo 'tools\preview_enhance.py') $local --recommend 2>&1
    $match = [regex]::Match(($advice | Out-String), 'RECOMMEND=(\w+)')
    if ($match.Success) {
        $chosenPreset = $match.Groups[1].Value
        Write-Host "preset chosen automatically: $chosenPreset" -ForegroundColor Cyan
        ($advice | Select-String -Pattern 'mean=' | Select-Object -Last 1) | ForEach-Object { Write-Host "  $_" }
    } else {
        $chosenPreset = 'bright'
        Write-Host "automation unavailable (-Preset auto), falling back to 'bright'" -ForegroundColor Yellow
    }
}

if ($chosenPreset) {
    $null = Invoke-Board "echo $chosenPreset > /tmp/hdmi_preset.txt"
    Write-Output "PRESET=$chosenPreset"
}

# --- 4) verify from the board's own state ------------------------------------------------
Start-Sleep -Seconds 3
$state = Invoke-Board "cat /tmp/hdmi_state.txt 2>/dev/null"
$running = Invoke-Board "ps -eo args= | grep -c '[h]dmi_resident'"

if (-not $running -or $running.Trim() -eq '0') {
    Write-Warning "the resident demo is not running, so nothing is streaming."
    Write-Host ""
    Write-Host "Start it once (and never restart it during a demo):" -ForegroundColor Yellow
    Write-Host "  ssh xilinx@192.168.2.99" -ForegroundColor Yellow
    Write-Host "  sudo env XILINX_XRT=/usr PATH=/usr/local/share/pynq-venv/bin:/usr/bin:/bin HOME=/root ``" -ForegroundColor Yellow
    Write-Host "    /usr/local/share/pynq-venv/bin/python3 -u hdmi_resident.py --image ruler_640x480.png" -ForegroundColor Yellow
    exit 1
}

$expected = "$uploadDir/$name"
$stateImage = ($state | Select-String -Pattern '^image=(.*)$' | Select-Object -First 1)
$stateValue = if ($stateImage) { $stateImage.Matches[0].Groups[1].Value } else { '' }

# Machine-readable results for callers such as upload_gui.ps1: Write-Host output goes to the
# console only, so a GUI that pipes this script's output would otherwise see nothing.
Write-Output "UPLOADED=$expected"
Write-Output "STATE_IMAGE=$stateValue"

if ($stateValue -eq $expected) {
    Write-Host "OK - the board is now showing $expected" -ForegroundColor Green
    $state | ForEach-Object { Write-Host "  $_" }
    if (-not $KeepLocal) { Remove-Item $local -ErrorAction SilentlyContinue }
    exit 0
}

Write-Warning "the board has not picked the new picture up yet. Its state is:"
$state | ForEach-Object { Write-Host "  $_" }
Write-Host ""
Write-Host "Wait a moment and check:  ssh xilinx@192.168.2.99 cat /tmp/hdmi_state.txt"
if (-not $KeepLocal) { Remove-Item $local -ErrorAction SilentlyContinue }
exit 2
