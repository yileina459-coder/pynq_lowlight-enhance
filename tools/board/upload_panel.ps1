<#
.SYNOPSIS
    上传到开发板 - 图片和视频合并在同一个窗口里。

.DESCRIPTION
    选一个文件，程序按扩展名（GIF / WebP 再看是否动图）判断是图片还是视频，只显示相关的选项：

      图片  : 比例（保持比例 / 裁切 / 拉伸）、增强挡位、是否在本机提亮、预览效果
      视频  : 播放方式（整段一个挡位 / 按场景切换 / 自己选）、帧率、时长

    然后点同一个按钮：图片是"上传并显示"，视频是"开始播放"。底层分别调用
    tools\board\show_image.ps1 和 tools\board\play_video.ps1，所以这里显示的成功/失败
    同样是**板上回报的真实状态**，不是命令发出去了就算成功。

    窗口下方是日志：会显示挡位选择、分段结果、板子的状态回读。出问题先看这里。

.PARAMETER File
    起始文件路径（可省略）。

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File tools\board\upload_panel.ps1
#>
[CmdletBinding()]
param(
    [string]$File = ''
)

# 'Continue'：ssh 会把 sudo 的提示写到 stderr，用 'Stop' 会把成功也当成错误。
$ErrorActionPreference = 'Continue'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$python = $env:PYTHON
if (-not $python) { $python = (Get-Command python -ErrorAction SilentlyContinue).Source }
if (-not $python) { $python = 'python' }
$board = 'xilinx@192.168.2.99'
$askpass = Join-Path $repo '.tmp\askpass\askpass.bat'
$showScript = Join-Path $repo 'tools\board\show_image.ps1'
$playScript = Join-Path $repo 'tools\board\play_video.ps1'
$ensureScript = Join-Path $repo 'tools\board\ensure_demo.ps1'
$demoStatusFile = Join-Path $repo '.tmp\demo_status.txt'

$env:SSH_ASKPASS = $askpass
$env:SSH_ASKPASS_REQUIRE = 'force'
$env:DISPLAY = ':0'

$imageExt = @('.jpg', '.jpeg', '.png', '.bmp', '.tif', '.tiff')
$animExt = @('.gif', '.webp')          # 可能是不动图，也可能是动图：要看帧数
$videoExt = @('.mp4', '.mov', '.mkv', '.avi', '.m4v', '.webm')

[System.Windows.Forms.Application]::EnableVisualStyles()

$form = New-Object System.Windows.Forms.Form
$form.Text = '上传到开发板（图片 / 视频）'
$form.StartPosition = 'CenterScreen'
$form.ClientSize = New-Object System.Drawing.Size(660, 580)
$form.FormBorderStyle = 'FixedDialog'
$form.MaximizeBox = $false
$form.Font = New-Object System.Drawing.Font('Microsoft YaHei UI', 9)

# --- 文件行 ---------------------------------------------------------------------------------
$labelFile = New-Object System.Windows.Forms.Label
$labelFile.Text = '文件：'
$labelFile.Location = New-Object System.Drawing.Point(16, 20)
$labelFile.AutoSize = $true
$form.Controls.Add($labelFile)

$textFile = New-Object System.Windows.Forms.TextBox
$textFile.Location = New-Object System.Drawing.Point(66, 17)
$textFile.Size = New-Object System.Drawing.Size(450, 24)
$textFile.Text = $File
$form.Controls.Add($textFile)

$btnBrowse = New-Object System.Windows.Forms.Button
$btnBrowse.Text = '浏览...'
$btnBrowse.Location = New-Object System.Drawing.Point(526, 15)
$btnBrowse.Size = New-Object System.Drawing.Size(118, 27)
$form.Controls.Add($btnBrowse)

$labelKind = New-Object System.Windows.Forms.Label
$labelKind.Location = New-Object System.Drawing.Point(66, 46)
$labelKind.AutoSize = $true
$labelKind.ForeColor = [System.Drawing.Color]::DimGray
$labelKind.Text = '等待选择文件（图片或视频都可以）'
$form.Controls.Add($labelKind)

# --- 图片选项 -------------------------------------------------------------------------------
$groupImage = New-Object System.Windows.Forms.GroupBox
$groupImage.Text = '图片选项'
$groupImage.Location = New-Object System.Drawing.Point(16, 72)
$groupImage.Size = New-Object System.Drawing.Size(628, 160)
$form.Controls.Add($groupImage)

$groupFit = New-Object System.Windows.Forms.GroupBox
$groupFit.Text = '比例'
$groupFit.Location = New-Object System.Drawing.Point(12, 20)
$groupFit.Size = New-Object System.Drawing.Size(280, 100)
$groupImage.Controls.Add($groupFit)

$radioLetter = New-Object System.Windows.Forms.RadioButton
$radioLetter.Text = '保持比例，四周留边'
$radioLetter.Location = New-Object System.Drawing.Point(10, 20)
$radioLetter.AutoSize = $true
$radioLetter.Checked = $true
$groupFit.Controls.Add($radioLetter)

$radioCrop = New-Object System.Windows.Forms.RadioButton
$radioCrop.Text = '裁切填满（照片）'
$radioCrop.Location = New-Object System.Drawing.Point(10, 44)
$radioCrop.AutoSize = $true
$groupFit.Controls.Add($radioCrop)

$radioStretch = New-Object System.Windows.Forms.RadioButton
$radioStretch.Text = '拉伸填满'
$radioStretch.Location = New-Object System.Drawing.Point(10, 68)
$radioStretch.AutoSize = $true
$groupFit.Controls.Add($radioStretch)

$labelPreset = New-Object System.Windows.Forms.Label
$labelPreset.Text = '增强挡位：'
$labelPreset.Location = New-Object System.Drawing.Point(306, 26)
$labelPreset.AutoSize = $true
$groupImage.Controls.Add($labelPreset)

$comboPreset = New-Object System.Windows.Forms.ComboBox
$comboPreset.Location = New-Object System.Drawing.Point(378, 23)
$comboPreset.Size = New-Object System.Drawing.Size(150, 24)
$comboPreset.DropDownStyle = 'DropDownList'
$script:presetItems = @(
    @{ Name = '自动（推荐）'; Value = 'auto' },
    @{ Name = '提亮 bright'; Value = 'bright' },
    @{ Name = '很暗 night'; Value = 'night' },
    @{ Name = '文档 document'; Value = 'document' },
    @{ Name = '阅读 reading'; Value = 'reading' },
    @{ Name = '只加对比 clarity'; Value = 'clarity' },
    @{ Name = '更锐利 crisp（文字页，照片会压暗部）'; Value = 'crisp' },
    @{ Name = '原图 pass'; Value = 'pass' },
    @{ Name = '反色 invert'; Value = 'invert' },
    @{ Name = '二值化 binarize'; Value = 'binarize' },
    @{ Name = '左右对比 split'; Value = 'split' }
)
foreach ($item in $script:presetItems) { [void]$comboPreset.Items.Add($item.Name) }
$comboPreset.SelectedIndex = 0
$groupImage.Controls.Add($comboPreset)

# 提亮在 PC 上做：板上的增益链路能工作，但 PC 侧的自适应曲线在暗图上效果更好也更稳。
$chkTone = New-Object System.Windows.Forms.CheckBox
$chkTone.Text = '在本机提亮（暗图推荐）'
$chkTone.Location = New-Object System.Drawing.Point(306, 54)
$chkTone.AutoSize = $true
$chkTone.Checked = $true
$groupImage.Controls.Add($chkTone)

$btnPreview = New-Object System.Windows.Forms.Button
$btnPreview.Text = '预览效果'
$btnPreview.Location = New-Object System.Drawing.Point(306, 80)
$btnPreview.Size = New-Object System.Drawing.Size(110, 28)
$groupImage.Controls.Add($btnPreview)

$hintImage = New-Object System.Windows.Forms.Label
$hintImage.Location = New-Object System.Drawing.Point(430, 84)
$hintImage.Size = New-Object System.Drawing.Size(186, 40)
$hintImage.ForeColor = [System.Drawing.Color]::Gray
$hintImage.Text = '预览只在本机生成对比图，不占用开发板。'
$groupImage.Controls.Add($hintImage)

# --- 视频选项 -------------------------------------------------------------------------------
$groupVideo = New-Object System.Windows.Forms.GroupBox
$groupVideo.Text = '视频选项'
$groupVideo.Location = New-Object System.Drawing.Point(16, 72)
$groupVideo.Size = New-Object System.Drawing.Size(628, 160)
$groupVideo.Visible = $false
$form.Controls.Add($groupVideo)

$radioClip = New-Object System.Windows.Forms.RadioButton
$radioClip.Text = '整段一个挡位（推荐，画面最稳）'
$radioClip.Location = New-Object System.Drawing.Point(14, 22)
$radioClip.AutoSize = $true
$radioClip.Checked = $true
$groupVideo.Controls.Add($radioClip)

$radioAdaptive = New-Object System.Windows.Forms.RadioButton
$radioAdaptive.Text = '按场景自动切换（视频里有明暗不同的片段）'
$radioAdaptive.Location = New-Object System.Drawing.Point(14, 46)
$radioAdaptive.AutoSize = $true
$groupVideo.Controls.Add($radioAdaptive)

$radioFixed = New-Object System.Windows.Forms.RadioButton
$radioFixed.Text = '我自己选挡位：'
$radioFixed.Location = New-Object System.Drawing.Point(14, 70)
$radioFixed.AutoSize = $true
$groupVideo.Controls.Add($radioFixed)

$comboVideoPreset = New-Object System.Windows.Forms.ComboBox
$comboVideoPreset.Location = New-Object System.Drawing.Point(140, 68)
$comboVideoPreset.Size = New-Object System.Drawing.Size(140, 24)
$comboVideoPreset.DropDownStyle = 'DropDownList'
foreach ($name in @('pass', 'clarity', 'bright', 'night', 'document', 'reading',
                    'invert', 'binarize', 'split')) {
    [void]$comboVideoPreset.Items.Add($name)
}
$comboVideoPreset.SelectedItem = 'clarity'
$comboVideoPreset.Enabled = $false
$groupVideo.Controls.Add($comboVideoPreset)

$labelFps = New-Object System.Windows.Forms.Label
$labelFps.Text = '帧率：'
$labelFps.Location = New-Object System.Drawing.Point(306, 26)
$labelFps.AutoSize = $true
$groupVideo.Controls.Add($labelFps)

$textFps = New-Object System.Windows.Forms.TextBox
$textFps.Location = New-Object System.Drawing.Point(352, 23)
$textFps.Size = New-Object System.Drawing.Size(46, 24)
$textFps.Text = '24'
$groupVideo.Controls.Add($textFps)

$labelSeconds = New-Object System.Windows.Forms.Label
$labelSeconds.Text = '时长（秒，0=整段）：'
$labelSeconds.Location = New-Object System.Drawing.Point(410, 26)
$labelSeconds.AutoSize = $true
$groupVideo.Controls.Add($labelSeconds)

$textSeconds = New-Object System.Windows.Forms.TextBox
$textSeconds.Location = New-Object System.Drawing.Point(552, 23)
$textSeconds.Size = New-Object System.Drawing.Size(46, 24)
$textSeconds.Text = '6'
$groupVideo.Controls.Add($textSeconds)

$chkLoop = New-Object System.Windows.Forms.CheckBox
$chkLoop.Text = '循环播放（默认只播一次，播完停在最后一帧）'
$chkLoop.Location = New-Object System.Drawing.Point(306, 136)
$chkLoop.AutoSize = $true
$chkLoop.Checked = $false
$groupVideo.Controls.Add($chkLoop)

$hintVideo = New-Object System.Windows.Forms.Label
$hintVideo.Location = New-Object System.Drawing.Point(306, 58)
$hintVideo.Size = New-Object System.Drawing.Size(306, 74)
$hintVideo.ForeColor = [System.Drawing.Color]::Gray
$hintVideo.Text = ("每帧占板上内存 0.9 MB，默认只取 6 秒。`r`n" +
                   "整段播放请把时长改 0（上限约 240 帧）。`r`n" +
                   "MP4/MOV/MKV 需要 ffmpeg（本机已配好）。")
$groupVideo.Controls.Add($hintVideo)

# --- 按钮与状态 -----------------------------------------------------------------------------
$btnGo = New-Object System.Windows.Forms.Button
$btnGo.Text = '上传并显示'
$btnGo.Location = New-Object System.Drawing.Point(16, 246)
$btnGo.Size = New-Object System.Drawing.Size(150, 38)
$form.Controls.Add($btnGo)

$btnStop = New-Object System.Windows.Forms.Button
$btnStop.Text = '停止播放'
$btnStop.Location = New-Object System.Drawing.Point(176, 246)
$btnStop.Size = New-Object System.Drawing.Size(110, 38)
$btnStop.Enabled = $false
$form.Controls.Add($btnStop)

$status = New-Object System.Windows.Forms.Label
$status.Location = New-Object System.Drawing.Point(300, 246)
$status.Size = New-Object System.Drawing.Size(344, 38)
$status.Text = '等待选择文件'
$status.ForeColor = [System.Drawing.Color]::DimGray
$form.Controls.Add($status)

# Restart whatever clip is already on the board. Pairs with the default play-once behaviour: a video
# that played through stays on its last frame, and this plays it again without re-uploading anything.
$btnReplay = New-Object System.Windows.Forms.Button
$btnReplay.Text = '重新播放'
$btnReplay.Location = New-Object System.Drawing.Point(16, 292)
$btnReplay.Size = New-Object System.Drawing.Size(110, 30)
$form.Controls.Add($btnReplay)

# --- 日志 -----------------------------------------------------------------------------------
$log = New-Object System.Windows.Forms.TextBox
$log.Location = New-Object System.Drawing.Point(16, 330)
$log.Size = New-Object System.Drawing.Size(628, 172)
$log.Multiline = $true
$log.ReadOnly = $true
$log.ScrollBars = 'Vertical'
$log.Font = New-Object System.Drawing.Font('Consolas', 9)
$log.Text = "选好文件后点上面的按钮。`r`n图片会直接显示在板子的 HDMI 输出上；视频会先在本机解码、分析、再播放。"
$form.Controls.Add($log)

$hint = New-Object System.Windows.Forms.Label
$hint.Location = New-Object System.Drawing.Point(16, 508)
$hint.Size = New-Object System.Drawing.Size(628, 62)
$hint.ForeColor = [System.Drawing.Color]::Gray
$hint.Text = ("屏幕出现彩条 = 采集卡丢了锁定，拔插一次 HDMI 线即可。`r`n" +
              "画面看起来是几段内容轮流出现 = 板子上的帧缓冲区残留，运行 tools\board\reset_board.ps1。`r`n" +
              "暗图请用「自动」或「提亮」；视频亮度不足时任何挡位都难以救回。")
$form.Controls.Add($hint)

# --- 逻辑 -----------------------------------------------------------------------------------
function Add-Log([string]$text) {
    $log.AppendText($text + "`r`n")
    $log.SelectionStart = $log.Text.Length
    $log.ScrollToCaret()
    $form.Refresh()
}

function Get-Kind([string]$path) {
    # 扩展名给出第一判断；GIF / WebP 可能是动图，交给 Pillow 数帧。
    $ext = [System.IO.Path]::GetExtension($path).ToLowerInvariant()
    if ($imageExt -contains $ext) { return 'image' }
    if ($videoExt -contains $ext) { return 'video' }
    if ($animExt -contains $ext) {
        if (-not $python) { return 'image' }
        $frames = & $python -c "import sys;from PIL import Image;im=Image.open(sys.argv[1]);print(getattr(im,'n_frames',1))" $path 2>$null
        if ($LASTEXITCODE -eq 0 -and $frames -and [int]$frames -gt 1) { return 'video' }
        return 'image'
    }
    return ''
}

function Show-For([string]$kind) {
    if ($kind -eq 'video') {
        $groupImage.Visible = $false
        $groupVideo.Visible = $true
        $btnGo.Text = '开始播放'
        $btnStop.Enabled = $true
        $labelKind.Text = '识别为：视频（会先在本机解码并分析，再在板上实时处理播放）'
    } else {
        $groupVideo.Visible = $false
        $groupImage.Visible = $true
        $btnGo.Text = '上传并显示'
        $btnStop.Enabled = $false
        $labelKind.Text = '识别为：图片'
    }
}

function Select-File([string]$path) {
    $textFile.Text = $path
    $kind = Get-Kind $path
    if ($kind -eq '') {
        $labelKind.Text = '这个扩展名不认识；图片请用 jpg/png/bmp，视频请用 mp4/mov/mkv/avi/gif'
        $labelKind.ForeColor = [System.Drawing.Color]::DarkRed
        return
    }
    $labelKind.ForeColor = [System.Drawing.Color]::DimGray
    Show-For $kind
}

$btnBrowse.Add_Click({
    $dialog = New-Object System.Windows.Forms.OpenFileDialog
    $dialog.Title = '选择要显示的图片或要播放的视频'
    $dialog.Filter = ('图片|*.jpg;*.jpeg;*.png;*.bmp;*.tif;*.tiff;*.gif;*.webp|' +
                      '视频|*.mp4;*.mov;*.mkv;*.avi;*.m4v;*.webm;*.gif;*.webp|所有文件|*.*')
    if ($dialog.ShowDialog() -eq 'OK') { Select-File $dialog.FileName }
})

$textFile.Add_TextChanged({
    if ($textFile.Text.Trim() -ne '') { Select-File $textFile.Text.Trim() }
})

$radioFixed.Add_CheckedChanged({ $comboVideoPreset.Enabled = $radioFixed.Checked })

$btnPreview.Add_Click({
    $path = $textFile.Text.Trim()
    if (-not (Test-Path $path)) {
        [System.Windows.Forms.MessageBox]::Show('请先选择一个存在的图片。', '预览', 'OK', 'Warning') | Out-Null
        return
    }
    $fit = if ($radioCrop.Checked) { 'crop' } elseif ($radioStretch.Checked) { 'stretch' } else { 'letterbox' }
    $picked = $script:presetItems | Where-Object { $_.Name -eq $comboPreset.SelectedItem } | Select-Object -First 1
    $presetValue = if ($picked) { $picked.Value } else { 'auto' }

    $work = Join-Path $repo '.tmp\upload'
    New-Item -ItemType Directory -Force -Path $work | Out-Null
    $prepared = Join-Path $work 'preview_src_640x480.png'
    $toneArgs = if ($chkTone.Checked) { @('--tone', 'page') } else { @() }
    & $python (@((Join-Path $repo 'tools\prepare_image.py'), $path, '--out', $prepared, '--fit', $fit) + $toneArgs) | Out-Null

    $sheet = Join-Path $work 'preview.png'
    if ($presetValue -eq 'auto') {
        & $python (Join-Path $repo 'tools\preview_enhance.py') $prepared --sheet --out $sheet | Out-Null
    } else {
        & $python (Join-Path $repo 'tools\preview_enhance.py') $prepared --preset $presetValue --out $sheet | Out-Null
    }
    if (Test-Path $sheet) {
        Add-Log "预览已生成：$sheet"
        Start-Process $sheet
    } else {
        Add-Log '预览生成失败，请确认 python 环境可用。'
    }
})

$btnReplay.Add_Click({
    $status.ForeColor = [System.Drawing.Color]::Black
    $status.Text = '正在重新播放...'
    $form.Refresh()
    try {
        & $playScript -Video 'x' -Replay 2>&1 | Out-Null
        Start-Sleep -Seconds 2
        $state = (& ssh -o StrictHostKeyChecking=no -o LogLevel=ERROR -o ConnectTimeout=10 `
                    $board 'cat /tmp/hdmi_state.txt' 2>$null | Out-String)
        if ($state -match 'playing=\d+') {
            $status.ForeColor = [System.Drawing.Color]::DarkGreen
            $status.Text = '重新播放中'
            Add-Log '[重新播放] ' + (($state -split "`n") | Where-Object { $_ -match 'playing=' })
        } else {
            $status.ForeColor = [System.Drawing.Color]::DarkRed
            $status.Text = '板子上没有可重播的片段'
            Add-Log '[重新播放] 板子上没有正在使用的片段，先上传一个视频。'
        }
    } catch {
        $status.ForeColor = [System.Drawing.Color]::DarkRed
        $status.Text = '重新播放失败'
        Add-Log ('[重新播放] 失败：' + $_.Exception.Message)
    }
})

$btnStop.Add_Click({
    $status.ForeColor = [System.Drawing.Color]::Black
    $status.Text = '正在停止...'
    $form.Refresh()
    try {
        & $playScript -Video 'x' -Stop 2>&1 | Out-Null
        $status.ForeColor = [System.Drawing.Color]::DarkGreen
        $status.Text = '已停止'
        Add-Log '已停止播放，板子回到静态图片。'
    } catch {
        $status.ForeColor = [System.Drawing.Color]::DarkRed
        $status.Text = '停止失败'
        Add-Log ("停止失败：" + $_.Exception.Message)
    }
})

$btnGo.Add_Click({
    $path = $textFile.Text.Trim()
    if (-not (Test-Path $path)) {
        [System.Windows.Forms.MessageBox]::Show('请先选择一个存在的文件。', '上传', 'OK', 'Warning') | Out-Null
        return
    }
    $kind = Get-Kind $path
    if ($kind -eq '') {
        [System.Windows.Forms.MessageBox]::Show('不认识的扩展名，无法判断是图片还是视频。', '上传',
            'OK', 'Warning') | Out-Null
        return
    }

    $btnGo.Enabled = $false
    $btnStop.Enabled = $false
    $status.ForeColor = [System.Drawing.Color]::Black
    $status.Text = '正在处理，请稍候...'
    Add-Log ('--- ' + (Get-Date -Format 'HH:mm:ss') + '  ' + $kind + '  ' + [System.IO.Path]::GetFileName($path))

    try {
        if ($kind -eq 'image') {
            $fit = if ($radioCrop.Checked) { 'crop' } elseif ($radioStretch.Checked) { 'stretch' } else { 'letterbox' }
            $picked = $script:presetItems | Where-Object { $_.Name -eq $comboPreset.SelectedItem } | Select-Object -First 1
            $presetArg = if ($picked) { $picked.Value } else { 'auto' }
            $toneArg = if ($chkTone.Checked) { 'page' } else { '' }
            Add-Log ("图片：比例 $fit，挡位 $presetArg，本机提亮 " + $(if ($chkTone.Checked) { '是' } else { '否' }))

            $output = & $showScript -Image $path -Fit $fit -Preset $presetArg -Tone $toneArg *>&1
            $raw = ($output | Out-String)
            $uploaded = [regex]::Match($raw, 'UPLOADED=(.+)').Groups[1].Value.Trim()
            $shown = [regex]::Match($raw, 'STATE_IMAGE=(.*)').Groups[1].Value.Trim()
            foreach ($line in ($raw -split "`n")) {
                if ($line.Trim()) { Add-Log ('  ' + $line.Trim()) }
            }
            if ($uploaded -and $uploaded -eq $shown) {
                $status.ForeColor = [System.Drawing.Color]::DarkGreen
                $status.Text = '上传成功，屏幕已换图'
            } else {
                $status.ForeColor = [System.Drawing.Color]::DarkRed
                $status.Text = '上传后板子状态不一致'
            }
        } else {
            $fps = 24.0
            if (-not [double]::TryParse($textFps.Text, [ref]$fps) -or $fps -le 0 -or $fps -gt 60) {
                [System.Windows.Forms.MessageBox]::Show('帧率请填 1~60 之间的数。', '播放', 'OK', 'Warning') | Out-Null
                return
            }
            $seconds = 6.0
            if (-not [double]::TryParse($textSeconds.Text, [ref]$seconds) -or $seconds -lt 0) {
                [System.Windows.Forms.MessageBox]::Show('时长请填 0 或正数。', '播放', 'OK', 'Warning') | Out-Null
                return
            }
            $playArgs = @{ Video = $path; Fps = $fps; Seconds = $seconds }
            if ($chkLoop.Checked) { $playArgs['Loop'] = $true }
            if ($radioFixed.Checked) {
                $playArgs['Preset'] = [string]$comboVideoPreset.SelectedItem
                Add-Log ("视频：固定挡位 " + $playArgs['Preset'] + "，帧率 $fps")
            } else {
                $playArgs['Auto'] = if ($radioAdaptive.Checked) { 'adaptive' } else { 'clip' }
                Add-Log ("视频：自动（" + $playArgs['Auto'] + "），帧率 $fps，时长 " +
                         $(if ($seconds -eq 0) { '整段' } else { "$seconds 秒" }))
            }

            $output = & $playScript @playArgs *>&1
            $raw = ($output | Out-String)
            foreach ($line in ($raw -split "`n")) {
                if ($line.Trim()) { Add-Log ('  ' + $line.Trim()) }
            }

            # 分析结果直接从分析器写的 JSON 里读，比抓控制台文本可靠。
            $analysisPath = Join-Path $repo '.tmp\clip_analysis\analysis.json'
            if ($playArgs.ContainsKey('Auto') -and (Test-Path $analysisPath)) {
                $data = Get-Content $analysisPath -Raw -Encoding UTF8 | ConvertFrom-Json
                Add-Log ("  分析：整段最高分 " + $data.clip_best + "，共 " + $data.segments.Count + " 段")
                foreach ($segment in $data.segments) {
                    Add-Log ("    帧 " + $segment.start + " .. " + ($segment.end - 1) +
                             "  (" + $segment.frames + " 帧)  " + $segment.preset)
                }
            }

            # 成功与否只看板子自己的状态文件。
            Start-Sleep -Seconds 4
            $state = (& ssh -o StrictHostKeyChecking=no -o LogLevel=ERROR -o ConnectTimeout=10 `
                        $board 'cat /tmp/hdmi_state.txt' 2>$null | Out-String)
            if ($state -match 'playing=\d+ frames, finished') {
                # Played through once and holding the last frame: success, not a fault.
                $status.ForeColor = [System.Drawing.Color]::DarkGreen
                $status.Text = '已播完（停在最后一帧，可点重新播放）'
            } elseif ($state -match 'playing=\d+') {
                $status.ForeColor = [System.Drawing.Color]::DarkGreen
                $status.Text = '正在播放'
            } elseif ($state.Trim() -ne '') {
                $status.ForeColor = [System.Drawing.Color]::DarkRed
                $status.Text = '板子没有开始播放'
            } else {
                $status.ForeColor = [System.Drawing.Color]::DarkRed
                $status.Text = '连不上板子'
            }
            if ($state.Trim() -ne '') {
                Add-Log '  板子报告：'
                foreach ($line in ($state -split "`n")) {
                    if ($line.Trim()) { Add-Log ('    ' + $line.Trim()) }
                }
            }
        }
    } catch {
        $status.ForeColor = [System.Drawing.Color]::DarkRed
        $status.Text = '出错了'
        Add-Log ('失败：' + $_.Exception.Message)
    } finally {
        $btnGo.Enabled = $true
        $btnStop.Enabled = ($kind -eq 'video')
    }
})

if ($File -ne '') { Select-File $File }

# --- 演示进程：打开窗口时自动检查 / 启动 ------------------------------------------------
# 面板假设演示进程在跑（它独占 VDMA）。没有它，任何上传都只会得到"板子没有开始播放"，
# 而用户无从知道要去 ssh 里起一个进程。这里交给 ensure_demo.ps1，用定时器读它的状态文件，
# 这样加载 overlay 的 40 秒里窗口不会卡住。
$script:lastDemoState = ''
$script:demoTimer = New-Object System.Windows.Forms.Timer
$script:demoTimer.Interval = 2000
$script:demoTimer.Add_Tick({
    if (-not (Test-Path $demoStatusFile)) { return }
    $raw = Get-Content $demoStatusFile -Raw -Encoding UTF8
    $state = [regex]::Match($raw, 'state=(\w+)').Groups[1].Value
    $message = [regex]::Match($raw, 'message=([^\r\n]*)').Groups[1].Value.Trim()
    if ($state -eq '' -or $state -eq $script:lastDemoState) { return }
    $script:lastDemoState = $state
    if ($message -ne '') { Add-Log ('[演示] ' + $message) }
    if ($state -eq 'running') {
        $script:demoTimer.Stop()
        if ($status.Text -eq '等待选择文件' -or $status.Text -like '*演示*') {
            $status.ForeColor = [System.Drawing.Color]::DarkGreen
            $status.Text = '演示就绪'
        }
    } elseif ($state -eq 'failed') {
        $script:demoTimer.Stop()
        $status.ForeColor = [System.Drawing.Color]::DarkRed
        $status.Text = '演示没起来，看下面日志'
    }
})

$form.Add_Shown({
    $form.Activate()
    if (Test-Path $ensureScript) {
        Add-Log '检查板子上的演示进程...'
        Start-Process -FilePath 'powershell' -WindowStyle Hidden -ArgumentList @(
            '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $ensureScript)
        $script:demoTimer.Start()
    }
})

[void]$form.ShowDialog()
$script:demoTimer.Stop()
