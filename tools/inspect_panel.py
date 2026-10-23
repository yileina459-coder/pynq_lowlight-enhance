"""Read the panel's own words: what kind did it think the file is, and what did it log?

Screenshots kept landing on the wrong window and the title is the same for both kinds, so the useful
question - "did it classify this file correctly?" - is answered from the text inside the window instead.

    python tools/inspect_panel.py
"""

from __future__ import annotations

import subprocess
import sys

PS = r'''
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
$root = [System.Windows.Automation.AutomationElement]::RootElement
$cond = New-Object System.Windows.Automation.PropertyCondition(
    [System.Windows.Automation.AutomationElement]::NameProperty, '上传到开发板（图片 / 视频）')
$win = $root.FindFirst([System.Windows.Automation.TreeScope]::Children, $cond)
if ($null -eq $win) { Write-Output 'NOWINDOW'; exit 1 }
$all = $win.FindAll([System.Windows.Automation.TreeScope]::Descendants,
                    [System.Windows.Automation.Condition]::TrueCondition)
foreach ($element in $all) {
    $name = $element.Current.Name
    if ($name -and ($name -like '*识别为*' -or $name -like '*挡位*' -or $name -like '*上传并显示*' -or
                    $name -like '*开始播放*' -or $name -like '*图片选项*' -or $name -like '*视频选项*' -or
                    $name -like '*等待选择*' -or $name -like '*.mp4' -or $name -like '*.png' -or
                    $name -like '*.gif')) {
        Write-Output ("TEXT|" + $element.Current.ControlType.ProgrammaticName + "|" + $name)
    }
}
Write-Output 'DONE'
'''


def main() -> int:
    result = subprocess.run(["powershell", "-NoProfile", "-Command", PS],
                            capture_output=True, text=True, encoding="utf-8",
                            errors="replace", timeout=90)
    output = ((result.stdout or "") + (result.stderr or "")).strip()
    if "NOWINDOW" in output:
        print("FAIL: no panel window open")
        return 1
    for line in output.splitlines():
        if line.startswith("TEXT|"):
            _, kind, text = line.split("|", 2)
            print(f"  [{kind.split('.')[-1]:12s}] {text}")
    print("DONE" if "DONE" in output else "incomplete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
