<#
.SYNOPSIS
    图片上传到开发板 - 图形界面，双击即用。

.DESCRIPTION
    选一张图片，选择保持比例 / 裁切填满 / 拉伸，点上传，板子的 HDMI 输出在 1~3 秒内换图。

    底层调用 tools\board\show_image.ps1（转换 -> 传输 -> 切换 -> 回读板上状态校验），
    所以这里显示的成功/失败同样是**板上回报的真实状态**，不是命令发出去了就算成功。

    支持三种打开方式：
      * 双击 上传图片.bat
      * 把图片直接拖到 上传图片.bat 上（跳过选择文件这一步）
      * 直接运行本脚本

.PARAMETER Image
    起始图片路径（可省略）。

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File tools\board\upload_gui.ps1
#>
[CmdletBinding()]
param(
    [string]$Image = '',
    [ValidateSet('letterbox', 'crop', 'stretch')][string]$Fit = 'letterbox'
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$showScript = Join-Path $repo 'tools\board\show_image.ps1'

[System.Windows.Forms.Application]::EnableVisualStyles()

$form = New-Object System.Windows.Forms.Form
$form.Text = '图片上传到开发板'
$form.StartPosition = 'CenterScreen'
$form.ClientSize = New-Object System.Drawing.Size(560, 250)
$form.FormBorderStyle = 'FixedDialog'
$form.MaximizeBox = $false
$form.Font = New-Object System.Drawing.Font('Microsoft YaHei UI', 9)

$labelImage = New-Object System.Windows.Forms.Label
$labelImage.Text = '图片：'
$labelImage.Location = New-Object System.Drawing.Point(16, 20)
$labelImage.AutoSize = $true
$form.Controls.Add($labelImage)

$textImage = New-Object System.Windows.Forms.TextBox
$textImage.Location = New-Object System.Drawing.Point(70, 17)
$textImage.Size = New-Object System.Drawing.Size(370, 24)
$textImage.Text = $Image
$form.Controls.Add($textImage)

$btnBrowse = New-Object System.Windows.Forms.Button
$btnBrowse.Text = '浏览...'
$btnBrowse.Location = New-Object System.Drawing.Point(450, 16)
$btnBrowse.Size = New-Object System.Drawing.Size(90, 26)
$form.Controls.Add($btnBrowse)

$group = New-Object System.Windows.Forms.GroupBox
$group.Text = '比例'
$group.Location = New-Object System.Drawing.Point(16, 56)
$group.Size = New-Object System.Drawing.Size(524, 64)
$form.Controls.Add($group)

$radioLetter = New-Object System.Windows.Forms.RadioButton
$radioLetter.Text = '保持比例，四周留边（文档、表格）'
$radioLetter.Location = New-Object System.Drawing.Point(12, 26)
$radioLetter.AutoSize = $true
$group.Controls.Add($radioLetter)

$radioCrop = New-Object System.Windows.Forms.RadioButton
$radioCrop.Text = '裁切填满（照片）'
$radioCrop.Location = New-Object System.Drawing.Point(250, 26)
$radioCrop.AutoSize = $true
$group.Controls.Add($radioCrop)

$radioStretch = New-Object System.Windows.Forms.RadioButton
$radioStretch.Text = '拉伸填满'
$radioStretch.Location = New-Object System.Drawing.Point(390, 26)
$radioStretch.AutoSize = $true
$group.Controls.Add($radioStretch)

switch ($Fit) {
    'crop'    { $radioCrop.Checked = $true }
    'stretch' { $radioStretch.Checked = $true }
    default   { $radioLetter.Checked = $true }
}

$btnUpload = New-Object System.Windows.Forms.Button
$btnUpload.Text = '上传到开发板'
$btnUpload.Location = New-Object System.Drawing.Point(16, 132)
$btnUpload.Size = New-Object System.Drawing.Size(160, 34)
$form.Controls.Add($btnUpload)

$status = New-Object System.Windows.Forms.Label
$status.Location = New-Object System.Drawing.Point(190, 132)
$status.Size = New-Object System.Drawing.Size(350, 34)
$status.Text = '等待选择图片'
$status.ForeColor = [System.Drawing.Color]::DimGray
$form.Controls.Add($status)

$hint = New-Object System.Windows.Forms.Label
$hint.Location = New-Object System.Drawing.Point(16, 180)
$hint.Size = New-Object System.Drawing.Size(524, 56)
$hint.ForeColor = [System.Drawing.Color]::Gray
$hint.Text = ("小提示：也可以把图片直接拖到 上传图片.bat 图标上，跳过选择这一步。`r`n" +
              "屏幕上如果出现彩条，是采集卡丢了锁定，拔插一次 HDMI 线就好。")
$form.Controls.Add($hint)

$btnBrowse.Add_Click({
    $dialog = New-Object System.Windows.Forms.OpenFileDialog
    $dialog.Title = '选择要显示的图片'
    $dialog.Filter = '图片文件|*.jpg;*.jpeg;*.png;*.bmp;*.gif;*.tif;*.tiff;*.webp|所有文件|*.*'
    if ($dialog.ShowDialog() -eq 'OK') { $textImage.Text = $dialog.FileName }
})

$btnUpload.Add_Click({
    $path = $textImage.Text.Trim()
    if ([string]::IsNullOrWhiteSpace($path)) {
        [System.Windows.Forms.MessageBox]::Show('请先选择一张图片。', '图片上传',
            'OK', 'Warning') | Out-Null
        return
    }
    if (-not (Test-Path $path)) {
        [System.Windows.Forms.MessageBox]::Show("找不到这个文件：`r`n$path", '图片上传',
            'OK', 'Warning') | Out-Null
        return
    }

    $fit = if ($radioCrop.Checked) { 'crop' } elseif ($radioStretch.Checked) { 'stretch' } else { 'letterbox' }

    $btnUpload.Enabled = $false
    $status.ForeColor = [System.Drawing.Color]::Black
    $status.Text = '正在转换并上传，请稍候...'
    $form.Refresh()

    try {
        $output = & $showScript -Image $path -Fit $fit 2>&1
        $raw = ($output | Out-String)
        $text = $raw.Trim()

        # show_image.ps1 prints STATE_IMAGE=<what the board reports>; comparing it with the file it
        # just uploaded is the only check that proves the picture actually changed on the board.
        $uploaded = [regex]::Match($raw, 'UPLOADED=(.+)').Groups[1].Value.Trim()
        $shown = [regex]::Match($raw, 'STATE_IMAGE=(.*)').Groups[1].Value.Trim()
        $ok = ($uploaded -ne '' -and $uploaded -eq $shown)

        if ($ok) {
            $status.ForeColor = [System.Drawing.Color]::DarkGreen
            $status.Text = '上传成功，屏幕已换图'
            [System.Windows.Forms.MessageBox]::Show(
                "上传成功，板子现在显示的是：`r`n$([System.IO.Path]::GetFileName($path))`r`n`r`n$text",
                '图片上传', 'OK', 'Information') | Out-Null
        } else {
            $status.ForeColor = [System.Drawing.Color]::DarkOrange
            $status.Text = '上传完成，但板上状态未确认'
            [System.Windows.Forms.MessageBox]::Show(
                "没有从板上回读到新图片的状态。`r`n`r`n$text",
                '图片上传', 'OK', 'Warning') | Out-Null
        }
    } catch {
        $status.ForeColor = [System.Drawing.Color]::Red
        $status.Text = '上传失败'
        [System.Windows.Forms.MessageBox]::Show("上传失败：`r`n$($_.Exception.Message)",
            '图片上传', 'OK', 'Error') | Out-Null
    } finally {
        $btnUpload.Enabled = $true
    }
})

# 允许把图片拖进窗口
$form.AllowDrop = $true
$form.Add_DragEnter({ param($s, $e) if ($e.Data.GetDataPresent('FileDrop')) { $e.Effect = 'Copy' } })
$form.Add_DragDrop({
    param($s, $e)
    $files = $e.Data.GetData('FileDrop')
    if ($files -and $files.Count -gt 0) { $textImage.Text = $files[0] }
})

# 直接带上图片路径时自动开始上传
if (-not [string]::IsNullOrWhiteSpace($Image)) {
    $form.Add_Shown({ $btnUpload.PerformClick() })
}

[System.Windows.Forms.Application]::Run($form) | Out-Null
