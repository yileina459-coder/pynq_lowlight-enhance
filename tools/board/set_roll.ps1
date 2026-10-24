<#
.SYNOPSIS
    让画面偏移归零：自动扫掠补偿值，或直接设定一个值。

.DESCRIPTION
    板子输出存在水平环绕（画面从源图的第 W 列开始），补偿量由 /tmp/hdmi_roll.txt 控制，常驻进程每帧读取，
    立即生效、不用重启。

    -Sweep  依次试 0、80、160 … 560，每档停 3 秒并打印当前值。看到画面对齐时按 Ctrl+C，
            然后把屏幕上最后打印的那个数字用 -Value 固定下来。
    -Value  直接设为某个值。

.EXAMPLE
    tools\board\set_roll.ps1 -Sweep
    tools\board\set_roll.ps1 -Value 240
#>
[CmdletBinding()]
param(
    [switch]$Sweep,
    [int]$Value = -1
)

$ErrorActionPreference = 'Continue'
$board = 'xilinx@192.168.2.99'
$repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$env:SSH_ASKPASS = Join-Path $repo '.tmp\askpass\askpass.bat'
$env:SSH_ASKPASS_REQUIRE = 'force'
$env:DISPLAY = ':0'

function Set-Roll([int]$n) {
    $wrapped = (($n % 640) + 640) % 640
    & ssh -o StrictHostKeyChecking=no -o LogLevel=ERROR -o ConnectTimeout=10 $board `
          "echo $wrapped > /tmp/hdmi_roll.txt" 2>$null | Out-Null
    return $wrapped
}

if ($Sweep) {
    Write-Host ""
    Write-Host "  依次尝试补偿值，看 HDMI 画面（或 OBS 预览）。对齐时按 Ctrl+C。" -ForegroundColor Cyan
    Write-Host "  记下最后显示的那个数字，再用 -Value 固定。" -ForegroundColor Cyan
    Write-Host ""
    foreach ($pass in 1..2) {
        foreach ($n in 0, 80, 160, 240, 320, 400, 480, 560) {
            $set = Set-Roll $n
            Write-Host ("  roll = {0,3}   ({1}/2 轮)" -f $set, $pass) -ForegroundColor Yellow
            Start-Sleep -Seconds 3
        }
    }
    Write-Host ""
    Write-Host "  扫掠结束。用 tools\board\set_roll.ps1 -Value <数字> 固定。" -ForegroundColor Green
    exit 0
}

if ($Value -ge 0) {
    $set = Set-Roll $Value
    Write-Host "  roll 已设为 $set" -ForegroundColor Green
    & ssh -o StrictHostKeyChecking=no -o LogLevel=ERROR -o ConnectTimeout=10 $board `
          "cat /tmp/hdmi_roll.txt" 2>$null | ForEach-Object { Write-Host "  板上确认为: $_" }
    exit 0
}

Write-Host "  用法: -Sweep  自动扫掠   或   -Value <0..639> 直接设定" -ForegroundColor Yellow
exit 1
