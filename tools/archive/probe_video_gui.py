"""Click the start button and read back what the window reports.

The window prints the failure into its own report box, so reading that box through UI Automation is
the fastest way to see it - much faster than guessing from the board's state. It also proves what a
user would actually be told.

    python tools/archive/probe_video_gui.py .tmp/userpic/scene.mp4
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

def _repo_root() -> Path:
    """The repository root: walk up until the directory that holds .git.

    tools/ used to be flat, so Path(__file__).parent.parent was the root. Scripts now live at different
    depths (tools/, tools/diag/, tools/archive/), and hard-coding the depth is exactly what broke when
    they moved - so the layout is discovered instead.
    """
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / ".git").exists():
            return parent
    return here.parents[2] if len(here.parents) > 2 else here.parent


REPO = _repo_root()
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(Path(__file__).resolve().parent))


PROBE_PS = r'''
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
Add-Type @'
using System;
using System.Runtime.InteropServices;
public class DshProbe {
    [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
    [DllImport("user32.dll")] public static extern void mouse_event(uint f, uint dx, uint dy, uint d, IntPtr e);
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
}
'@
$root = [System.Windows.Automation.AutomationElement]::RootElement
$winCond = New-Object System.Windows.Automation.PropertyCondition(
    [System.Windows.Automation.AutomationElement]::NameProperty, 'TITLE_TEXT')
$win = $root.FindFirst([System.Windows.Automation.TreeScope]::Children, $winCond)
if ($null -eq $win) { Write-Output 'NOWINDOW'; exit 1 }

$btnCond = New-Object System.Windows.Automation.PropertyCondition(
    [System.Windows.Automation.AutomationElement]::NameProperty, 'BUTTON_TEXT')
$btn = $win.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $btnCond)
if ($null -eq $btn) { Write-Output 'NOBUTTON'; exit 1 }
$rect = $btn.Current.BoundingRectangle
[void][DshProbe]::SetForegroundWindow($win.Current.NativeWindowHandle)
Start-Sleep -Milliseconds 300
[void][DshProbe]::SetCursorPos([int]($rect.Left + $rect.Width / 2), [int]($rect.Top + $rect.Height / 2))
Start-Sleep -Milliseconds 200
[DshProbe]::mouse_event(0x0002, 0, 0, 0, [IntPtr]::Zero)
Start-Sleep -Milliseconds 80
[DshProbe]::mouse_event(0x0004, 0, 0, 0, [IntPtr]::Zero)
Write-Output 'CLICKED'
'''

READ_PS = r'''
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
$root = [System.Windows.Automation.AutomationElement]::RootElement
$winCond = New-Object System.Windows.Automation.PropertyCondition(
    [System.Windows.Automation.AutomationElement]::NameProperty, 'TITLE_TEXT')
$win = $root.FindFirst([System.Windows.Automation.TreeScope]::Children, $winCond)
if ($null -eq $win) { Write-Output 'NOWINDOW'; exit 1 }
$editCond = New-Object System.Windows.Automation.PropertyCondition(
    [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
    [System.Windows.Automation.ControlType]::Edit)
$edits = $win.FindAll([System.Windows.Automation.TreeScope]::Descendants, $editCond)
$found = 0
foreach ($element in $edits) {
    $value = ''
    try {
        $pattern = $element.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)
        $value = $pattern.Current.Value
    } catch { $value = '(no value pattern)' }
    if ($value -match '---|失败|正在|分析|挡位|视频：') {
        Write-Output 'REPORT_BEGIN'
        Write-Output $value
        Write-Output 'REPORT_END'
        $found = 1
    }
}
if (-not $found) { Write-Output 'NOREPORT' }
'''


def run_ps(script: str, timeout: int = 90) -> str:
    script = script.replace("TITLE_TEXT", "视频播放（自动选挡位）").replace("BUTTON_TEXT", "开始播放")
    result = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                             "-Command", script],
                            capture_output=True, text=True, encoding="utf-8",
                            errors="replace", timeout=timeout)
    return ((result.stdout or "") + (result.stderr or "")).strip()


def main(argv: list[str]) -> int:
    video = argv[0] if argv else str(REPO / ".tmp" / "userpic" / "scene.mp4")
    gui = REPO / "tools" / "board" / "video_gui.ps1"

    run_ps(r'''
$p = Get-Process powershell -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle -like '*视频播放*' } | Select-Object -First 1
if ($p) { $p.CloseMainWindow() | Out-Null }
''')
    subprocess.Popen(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                      "-File", str(gui), "-Video", video])
    time.sleep(7)

    click = run_ps(PROBE_PS)
    print("click:", click.splitlines()[0] if click else "(nothing)")

    for wait in (10, 15, 20):
        time.sleep(wait)
        report = run_ps(READ_PS)
        print(f"\n--- report after {wait}s more ---")
        print(report[:1600])
        if "失败" in report or "REPORT" in report and "---" in report:
            if "失败" in report:
                break
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
