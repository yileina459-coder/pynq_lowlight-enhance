<#
.SYNOPSIS
    自动测量并消除 HDMI 输出的水平偏移（不用再blindly扫值）。

.DESCRIPTION
    板子的输出会整体水平环绕：画面不是"右边黑一块"，而是从源图的某一列开始、转一圈接回去。
    原因是输出核需要的 SOF 标记由板上 axis_sof_gen 按行数重新生成，锚点落在像素流启动的那一刻，
    所以相位是"这一路像素流"的属性：

        * 换图、换挡位、常驻进程每 200 ms 的重推  —— 相位不变（实测每次都一样）
        * 常驻进程重启 / 板子重启               —— 相位重新掷一次

    于是正确做法不是猜一个值，而是启动完演示后测一次。这个脚本调用 tools\board\align_output.py：
    显示八色彩条 → 从 OBS 预览读回 → 按色相算出环绕量 → 写入 /tmp/hdmi_roll.txt → 再测一次确认残差为 0
    → 把原来的图和挡位放回去。

    前提：OBS 正在预览采集卡（板子的输出只有这一个"眼睛"）。运行期间 OBS 窗口会短暂被提到最前，
    结束后恢复。

.PARAMETER Measure
    只报告当前画面的环绕量，不做任何修改。

.EXAMPLE
    tools\board\fix_offset.ps1
    tools\board\fix_offset.ps1 -Measure
#>
[CmdletBinding()]
param(
    [switch]$Measure
)

$ErrorActionPreference = 'Continue'
$repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$script = Join-Path $repo 'tools\board\align_output.py'

# 与 show_image.ps1 用同一个 Python（Pillow + numpy 都装在它里面），找不到就退回 PATH 里的 python。
$python = $env:PYTHON
if (-not $python) { $python = (Get-Command python -ErrorAction SilentlyContinue).Source }
if (-not $python) { $python = 'python' }
if (-not $python) { throw 'python not found: add Python 3 to PATH or set $env:PYTHON' }

if (-not (Test-Path $script)) { throw "缺少 $script" }

$arguments = @($script)
if ($Measure) { $arguments += '--measure' }

& $python @arguments
exit $LASTEXITCODE
