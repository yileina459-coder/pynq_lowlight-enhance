<#
.SYNOPSIS
    确保板子上的演示进程在运行；没运行就启动它。

.DESCRIPTION
    上传面板假设"演示进程已经在跑"，否则任何上传都只会得到"板子没有开始播放"。这个脚本补上这一步：

      1. 查板上有没有 hdmi_resident 在跑；
      2. 没有就在后台启动它（nohup，不占用原来的终端）；
      3. 等 /tmp/hdmi_state.txt 出现，最多等 150 秒；
      4. 把结论写进 .tmp\demo_status.txt，供面板轮询。

    为什么不用"启动后马上返回"：PYNQ 加载 overlay 要 ~40 秒，模式编程和 VDMA 启动再几秒，
    这期间读状态文件会失败——直接返回会让人以为启动失败。

    **已知限制**：如果是"演示正在跑 → 被强行杀掉"之后再启动，采集卡会丢锁（屏幕变彩条），
    这种情况需要重启板子。脚本检测到"启动了但状态文件一直不出现"时会提示这一点。

.PARAMETER WaitSeconds
    最多等多久（默认 150 秒）。

.EXAMPLE
    tools\board\ensure_demo.ps1
#>
[CmdletBinding()]
param(
    [int]$WaitSeconds = 150
)

$ErrorActionPreference = 'Continue'
$repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$board = 'xilinx@192.168.2.99'
$askpass = Join-Path $repo '.tmp\askpass\askpass.bat'
$statusFile = Join-Path $repo '.tmp\demo_status.txt'
$appDir = '/home/xilinx/jupyter_notebooks/hdmi_enh2'

$env:SSH_ASKPASS = $askpass
$env:SSH_ASKPASS_REQUIRE = 'force'
$env:DISPLAY = ':0'

function Write-Status([string]$state, [string]$message) {
    $line = "state=$state`nmessage=$message`nupdated=" + (Get-Date -Format 'HH:mm:ss')
    New-Item -ItemType Directory -Force -Path (Split-Path $statusFile) | Out-Null
    [System.IO.File]::WriteAllText($statusFile, $line + "`n", (New-Object System.Text.UTF8Encoding($false)))
    Write-Host $message
}

function Invoke-Board([string]$command, [int]$timeout = 25) {
    $output = & ssh -o StrictHostKeyChecking=no -o LogLevel=ERROR -o ConnectTimeout=$timeout `
                    $board $command 2>$null
    return ($output | Out-String)
}

if (-not (Test-Path $askpass)) {
    Write-Status 'failed' "缺少 $askpass（ssh 自动填密码用），无法连接板子"
    exit 1
}

# 1) 板子通不通
$ping = Test-Connection -ComputerName 192.168.2.99 -Count 1 -Quiet -ErrorAction SilentlyContinue
if (-not $ping) {
    Write-Status 'failed' '板子没有响应（ping 不通）。请确认电源和网线，或重启板子。'
    exit 1
}

# 2) 演示在不在跑
$count = (Invoke-Board 'ps -eo args= | grep -c "[h]dmi_resident"').Trim()
if ($count -match '^[1-9]') {
    Write-Status 'running' '演示进程已在运行'
    exit 0
}

# 3) 没跑就启动（nohup：ssh 断开后继续跑）
Write-Status 'starting' '演示进程没在运行，正在启动（约 40~60 秒）...'
$start = "cd $appDir && echo xilinx | sudo -S env XILINX_XRT=/usr " +
         "PATH=/usr/local/share/pynq-venv/bin:/usr/bin:/bin HOME=/root " +
         "nohup /usr/local/share/pynq-venv/bin/python3 -u hdmi_resident.py " +
         "--image testcard_640x480.png --roll 0 --preset clarity " +
         "> /tmp/res_panel.log 2>&1 & echo started"
$null = Invoke-Board $start

# 4) 等状态文件出现并变新
$deadline = (Get-Date).AddSeconds($WaitSeconds)
$seen = $false
while ((Get-Date) -lt $deadline) {
    Start-Sleep -Seconds 4
    $state = Invoke-Board 'cat /tmp/hdmi_state.txt 2>/dev/null'
    if ($state -match 'mode=\d+x\d+') {
        $seen = $true
        break
    }
    Write-Status 'starting' '正在启动演示（加载 overlay 中）...'
}

if ($seen) {
    Write-Status 'running' '演示已启动'
    exit 0
}

# 5) 启动失败：给出可执行的建议，而不是只说"失败"
$log = Invoke-Board 'tail -6 /tmp/res_panel.log 2>/dev/null'
Write-Status 'failed' ("演示启动后没有回报状态。可能是采集卡丢锁（屏幕彩条）——请重启板子后再试。`n" +
                       "板上日志末尾：`n" + ($log.Trim()))
exit 2
