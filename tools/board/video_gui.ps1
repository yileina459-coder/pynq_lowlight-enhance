<#
.SYNOPSIS
    视频上传到开发板 - 图形界面，双击即用。

.DESCRIPTION
    选一段视频，选择播放方式，点开始播放：程序在 PC 上解码、分析整段视频、自动挑挡位，
    然后在板子的 FPGA 上实时处理播放，整个过程不重启演示进程。

    三种播放方式：
      * 整段一个挡位（推荐）  分析后取"整段平均最清晰"的挡位，画面绝对稳定；
      * 按场景自动切换        只在真正的场景切换处换挡，段间不闪烁；
      * 我自己选挡位          跳过分析，用下拉框里指定的挡位。

    为什么分析放在 PC 上：板子的 PS 用 numpy 处理一帧要 3 秒，而 PC 分析一帧几十毫秒；
    分析结果是"每帧用哪个挡位"的排程，板上按排程实时切换（切挡不中断像素流）。

    播放用的帧会写进板子 DDR，每帧 0.9 MB，所以默认只取 6 秒；要整段请把「时长」改成 0
    （最长约 240 帧，约 215 MB）。

.PARAMETER Video
    起始视频路径（可省略）。

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File tools\board\video_gui.ps1
#>
[CmdletBinding()]
param(
    [string]$Video = ''
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$playScript = Join-Path $repo 'tools\board\play_video.ps1'

[System.Windows.Forms.Application]::EnableVisualStyles()

$form = New-Object System.Windows.Forms.Form
$form.Text = '视频播放（自动选挡位）'
$form.StartPosition = 'CenterScreen'
$form.ClientSize = New-Object System.Drawing.Size(620, 470)
$form.FormBorderStyle = 'FixedDialog'
$form.MaximizeBox = $false
$form.Font = New-Object System.Drawing.Font('Microsoft YaHei UI', 9)

# --- file row -------------------------------------------------------------------------------
$labelVideo = New-Object System.Windows.Forms.Label
$labelVideo.Text = '视频：'
$labelVideo.Location = New-Object System.Drawing.Point(16, 20)
$labelVideo.AutoSize = $true
$form.Controls.Add($labelVideo)

$textVideo = New-Object System.Windows.Forms.TextBox
$textVideo.Location = New-Object System.Drawing.Point(70, 17)
$textVideo.Size = New-Object System.Drawing.Size(420, 24)
$textVideo.Text = $Video
$form.Controls.Add($textVideo)

$btnBrowse = New-Object System.Windows.Forms.Button
$btnBrowse.Text = '浏览...'
$btnBrowse.Location = New-Object System.Drawing.Point(500, 15)
$btnBrowse.Size = New-Object System.Drawing.Size(100, 27)
$form.Controls.Add($btnBrowse)

# --- playback mode --------------------------------------------------------------------------
$groupMode = New-Object System.Windows.Forms.GroupBox
$groupMode.Text = '播放方式'
$groupMode.Location = New-Object System.Drawing.Point(16, 52)
$groupMode.Size = New-Object System.Drawing.Size(584, 92)
$form.Controls.Add($groupMode)

$radioClip = New-Object System.Windows.Forms.RadioButton
$radioClip.Text = '整段一个挡位（推荐，画面最稳）'
$radioClip.Location = New-Object System.Drawing.Point(14, 22)
$radioClip.AutoSize = $true
$radioClip.Checked = $true
$groupMode.Controls.Add($radioClip)

$radioAdaptive = New-Object System.Windows.Forms.RadioButton
$radioAdaptive.Text = '按场景自动切换（视频里有明暗不同的片段时用）'
$radioAdaptive.Location = New-Object System.Drawing.Point(14, 46)
$radioAdaptive.AutoSize = $true
$groupMode.Controls.Add($radioAdaptive)

$radioFixed = New-Object System.Windows.Forms.RadioButton
$radioFixed.Text = '我自己选挡位：'
$radioFixed.Location = New-Object System.Drawing.Point(14, 68)
$radioFixed.AutoSize = $true
$groupMode.Controls.Add($radioFixed)

$comboPreset = New-Object System.Windows.Forms.ComboBox
$comboPreset.Location = New-Object System.Drawing.Point(180, 66)
$comboPreset.Size = New-Object System.Drawing.Size(200, 24)
$comboPreset.DropDownStyle = 'DropDownList'
$script:presets = @(
    'pass', 'clarity', 'bright', 'night', 'document', 'reading', 'invert', 'binarize', 'split'
)
foreach ($name in $script:presets) { [void]$comboPreset.Items.Add($name) }
$comboPreset.SelectedItem = 'clarity'
$comboPreset.Enabled = $false
$groupMode.Controls.Add($comboPreset)

# --- fps / seconds --------------------------------------------------------------------------
$labelFps = New-Object System.Windows.Forms.Label
$labelFps.Text = '帧率：'
$labelFps.Location = New-Object System.Drawing.Point(16, 158)
$labelFps.AutoSize = $true
$form.Controls.Add($labelFps)

$textFps = New-Object System.Windows.Forms.TextBox
$textFps.Location = New-Object System.Drawing.Point(70, 155)
$textFps.Size = New-Object System.Drawing.Size(50, 24)
$textFps.Text = '24'
$form.Controls.Add($textFps)

$labelSeconds = New-Object System.Windows.Forms.Label
$labelSeconds.Text = '时长（秒，0 = 整段）：'
$labelSeconds.Location = New-Object System.Drawing.Point(140, 158)
$labelSeconds.AutoSize = $true
$form.Controls.Add($labelSeconds)

$textSeconds = New-Object System.Windows.Forms.TextBox
$textSeconds.Location = New-Object System.Drawing.Point(290, 155)
$textSeconds.Size = New-Object System.Drawing.Size(50, 24)
$textSeconds.Text = '6'
$form.Controls.Add($textSeconds)

# --- buttons --------------------------------------------------------------------------------
$btnStart = New-Object System.Windows.Forms.Button
$btnStart.Text = '开始播放'
$btnStart.Location = New-Object System.Drawing.Point(16, 190)
$btnStart.Size = New-Object System.Drawing.Size(150, 36)
$form.Controls.Add($btnStart)

$btnStop = New-Object System.Windows.Forms.Button
$btnStop.Text = '停止播放'
$btnStop.Location = New-Object System.Drawing.Point(176, 190)
$btnStop.Size = New-Object System.Drawing.Size(120, 36)
$form.Controls.Add($btnStop)

$status = New-Object System.Windows.Forms.Label
$status.Location = New-Object System.Drawing.Point(310, 190)
$status.Size = New-Object System.Drawing.Size(294, 36)
$status.Text = '等待选择视频'
$status.ForeColor = [System.Drawing.Color]::DimGray
$form.Controls.Add($status)

# --- report box -----------------------------------------------------------------------------
$report = New-Object System.Windows.Forms.TextBox
$report.Location = New-Object System.Drawing.Point(16, 236)
$report.Size = New-Object System.Drawing.Size(584, 150)
$report.Multiline = $true
$report.ReadOnly = $true
$report.ScrollBars = 'Vertical'
$report.Font = New-Object System.Drawing.Font('Consolas', 9)
$report.Text = '选好视频后点「开始播放」。' + "`r`n" +
               '会先在本机解码并分析整段视频（每帧几十毫秒），再把帧和挡位排程传到板子。'
$form.Controls.Add($report)

$hint = New-Object System.Windows.Forms.Label
$hint.Location = New-Object System.Drawing.Point(16, 392)
$hint.Size = New-Object System.Drawing.Size(584, 68)
$hint.ForeColor = [System.Drawing.Color]::Gray
$hint.Text = ("MP4 / MOV / MKV 需要 ffmpeg（本机已在 .tmp\tools\ffmpeg.exe）；GIF、动态 WebP 不需要。`r`n" +
              "板子 DDR 有限：每帧 0.9 MB，默认取 6 秒；整段播放请把时长改 0（上限约 240 帧）。`r`n" +
              "屏幕出现彩条是采集卡丢了锁定，拔插一次 HDMI 线即可；播放中调参只需改 /tmp 里的文本文件。")
$form.Controls.Add($hint)

# --- behaviour ------------------------------------------------------------------------------
$btnBrowse.Add_Click({
    $dialog = New-Object System.Windows.Forms.OpenFileDialog
    $dialog.Title = '选择要播放的视频'
    $dialog.Filter = '视频文件|*.mp4;*.mov;*.mkv;*.avi;*.gif;*.webp|所有文件|*.*'
    if ($dialog.ShowDialog() -eq 'OK') { $textVideo.Text = $dialog.FileName }
})

$radioFixed.Add_CheckedChanged({
    $comboPreset.Enabled = $radioFixed.Checked
})

$btnStop.Add_Click({
    $status.ForeColor = [System.Drawing.Color]::Black
    $status.Text = '正在停止...'
    $form.Refresh()
    try {
        & $playScript -Video 'x' -Stop 2>&1 | Out-Null
        $status.ForeColor = [System.Drawing.Color]::DarkGreen
        $status.Text = '已停止，回到静态画面'
        $report.AppendText("`r`n已停止播放，板子回到静态图片。`r`n")
    } catch {
        $status.ForeColor = [System.Drawing.Color]::DarkRed
        $status.Text = '停止失败'
        $report.AppendText("`r`n停止失败：$($_.Exception.Message)`r`n")
    }
})

$btnStart.Add_Click({
    $path = $textVideo.Text.Trim()
    if ([string]::IsNullOrWhiteSpace($path) -or -not (Test-Path $path)) {
        [System.Windows.Forms.MessageBox]::Show('请先选择一段存在的视频。', '视频播放',
            'OK', 'Warning') | Out-Null
        return
    }
    $fps = 24.0
    if (-not [double]::TryParse($textFps.Text, [ref]$fps) -or $fps -le 0 -or $fps -gt 60) {
        [System.Windows.Forms.MessageBox]::Show('帧率请填 1~60 之间的数。', '视频播放',
            'OK', 'Warning') | Out-Null
        return
    }
    $seconds = 6.0
    if (-not [double]::TryParse($textSeconds.Text, [ref]$seconds) -or $seconds -lt 0) {
        [System.Windows.Forms.MessageBox]::Show('时长请填 0 或正数（0 表示整段）。', '视频播放',
            'OK', 'Warning') | Out-Null
        return
    }

    $playArgs = @{ Video = $path; Fps = $fps; Seconds = $seconds }
    if ($radioFixed.Checked) {
        $playArgs['Preset'] = [string]$comboPreset.SelectedItem
    } else {
        $playArgs['Auto'] = if ($radioAdaptive.Checked) { 'adaptive' } else { 'clip' }
    }

    $btnStart.Enabled = $false
    $btnStop.Enabled = $false
    $report.Clear()
    $status.ForeColor = [System.Drawing.Color]::Black
    $status.Text = '正在解码并分析视频，请稍候...'
    $report.AppendText("视频：$path`r`n")
    $report.AppendText(("方式：{0}，帧率 {1:g} fps，时长 {2}`r`n" -f
        $(if ($playArgs.ContainsKey('Auto')) { "自动（$($playArgs['Auto'])）" } else { "固定挡位 $($playArgs['Preset'])" }),
        $fps, $(if ($seconds -eq 0) { '整段' } else { "$seconds 秒" })))
    $report.AppendText("`r`n--- 开始 ---`r`n")
    $form.Refresh()

    try {
        # Splat the hashtable we built. It must be @playArgs, not @args: inside a Click handler the
        # automatic $args holds the event arguments (sender, MouseEventArgs), and splatting that array
        # passes them positionally - which is exactly how "-Fps" once received a MouseEventArgs.
        # *>&1 captures every stream. 2>&1 alone misses Write-Host, which goes to the information
        # stream in PowerShell 5.1 - that is why the report box looked empty and why the status said
        # "没能开始播放" while the board was already playing.
        $output = & $playScript @playArgs *>&1
        $text = ($output | Out-String)

        # Show the analyser's own summary, if it ran. Reading the JSON it wrote is more reliable than
        # scraping console text, and it gives the operator the actual segment list.
        $analysisPath = Join-Path $repo '.tmp\clip_analysis\analysis.json'
        if ($playArgs.ContainsKey('Auto') -and (Test-Path $analysisPath)) {
            $data = Get-Content $analysisPath -Raw -Encoding UTF8 | ConvertFrom-Json
            $report.AppendText("分析结果：整段平均最高分 = $($data.clip_best)`r`n")
            $report.AppendText("挡位分段（共 $($data.segments.Count) 段）：`r`n")
            foreach ($segment in $data.segments) {
                $report.AppendText(("  帧 {0,4} .. {1,4}  ({2,3} 帧)   {3}`r`n" -f
                    $segment.start, ($segment.end - 1), $segment.frames, $segment.preset))
            }
            $report.AppendText("`r`n")
        }

        # Ask the board. Grepping the console output was wrong twice over: Write-Host is not
        # capturable with 2>&1, and the process printing "playing" is not proof that pixels flow.
        $boardState = ''
        try {
            $env:SSH_ASKPASS = Join-Path $repo '.tmp\askpass\askpass.bat'
            $env:SSH_ASKPASS_REQUIRE = 'force'
            $env:DISPLAY = ':0'
            $boardState = (& ssh -o StrictHostKeyChecking=no -o LogLevel=ERROR `
                              -o ConnectTimeout=10 'xilinx@192.168.2.99' `
                              'cat /tmp/hdmi_state.txt' 2>$null | Out-String)
        } catch {
            $boardState = ''
        }
        $playing = [regex]::Match($boardState, 'playing=\d+').Success
        if ($playing) {
            $status.ForeColor = [System.Drawing.Color]::DarkGreen
            $status.Text = '正在播放'
        } elseif ($boardState -ne '') {
            $status.ForeColor = [System.Drawing.Color]::DarkRed
            $status.Text = '板子没有开始播放'
        } else {
            $status.ForeColor = [System.Drawing.Color]::DarkRed
            $status.Text = '连不上板子'
        }
        # Record the verdict. A file is testable without screenshotting the window, and when an
        # operator reports "it says it failed" this says exactly what the window believed and why.
        try {
            $statusPath = Join-Path $repo '.tmp\video_gui_status.txt'
            $lines = @(
                "status=" + $status.Text,
                "playing=" + $playing,
                "video=" + $path,
                "mode=" + $(if ($playArgs.ContainsKey('Auto')) { $playArgs['Auto'] } else { 'fixed:' + $playArgs['Preset'] }),
                "board_state_begin",
                $boardState.Trim(),
                "board_state_end"
            )
            [System.IO.File]::WriteAllLines($statusPath, $lines, (New-Object System.Text.UTF8Encoding($false)))
        } catch {
            # Never let bookkeeping break the window.
        }

        if ($boardState -ne '') {
            $report.AppendText("板子报告：`r`n")
            foreach ($line in ($boardState -split "`n")) {
                if ($line.Trim()) { $report.AppendText("  " + $line.Trim() + "`r`n") }
            }
            $report.AppendText("`r`n")
        }
        $report.AppendText($text.Trim())
        $report.SelectionStart = $report.Text.Length
        $report.ScrollToCaret()
    } catch {
        $status.ForeColor = [System.Drawing.Color]::DarkRed
        $status.Text = '出错了'
        $report.AppendText("`r`n失败：$($_.Exception.Message)`r`n")
    } finally {
        $btnStart.Enabled = $true
        $btnStop.Enabled = $true
    }
})

$form.Add_Shown({ $form.Activate() })
[void]$form.ShowDialog()
