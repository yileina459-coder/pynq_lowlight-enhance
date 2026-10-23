"""Click the start button, wait, and photograph the window as evidence.

UI Automation can find and click the button, but it cannot tell me what the operator sees. A window
screenshot is the closest thing to standing in front of the machine, so this combines the click with a
capture of the window itself.

    python tools/test_video_gui.py .tmp/userpic/scene.mp4
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

CLICK_PS = r'''
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes, System.Windows.Forms
Add-Type @'
using System;
using System.Runtime.InteropServices;
public class DshClick {
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
# Focusing the button and pressing space is immune to DPI scaling: an earlier version computed a
# cursor position from the UIA bounds and the click landed outside the button on this screen.
[void][DshClick]::SetForegroundWindow($win.Current.NativeWindowHandle)
Start-Sleep -Milliseconds 400
$btn.SetFocus()
Start-Sleep -Milliseconds 300
Write-Output ("FOCUSED " + $btn.Current.Name)
[System.Windows.Forms.SendKeys]::SendWait(' ')
Write-Output 'CLICKED'
'''

SHOT_PS = r'''
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Add-Type -AssemblyName System.Windows.Forms, System.Drawing
Add-Type @'
using System;
using System.Runtime.InteropServices;
public class DshShot {
    [StructLayout(LayoutKind.Sequential)] public struct RECT { public int L,T,R,B; }
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
}
'@
$p = Get-Process powershell -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle -like '*视频播放*' } | Select-Object -First 1
if (-not $p) { Write-Output 'NOWINDOW'; exit 1 }
[void][DshShot]::SetForegroundWindow($p.MainWindowHandle)
Start-Sleep -Milliseconds 500
$r = New-Object DshShot+RECT
[void][DshShot]::GetWindowRect($p.MainWindowHandle, [ref]$r)
$w = $r.R - $r.L
$h = $r.B - $r.T
$bmp = New-Object System.Drawing.Bitmap $w, $h
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($r.L, $r.T, 0, 0, (New-Object System.Drawing.Size($w, $h)))
$bmp.Save(SHOT_PATH, [System.Drawing.Imaging.ImageFormat]::Png)
$g.Dispose()
$bmp.Dispose()
Write-Output ("SAVED {0}x{1}" -f $w, $h)
'''


def run_ps(script: str, timeout: int = 120) -> str:
    script = (script.replace("TITLE_TEXT", "视频播放（自动选挡位）")
                    .replace("BUTTON_TEXT", "开始播放"))
    result = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                             "-Command", script],
                            capture_output=True, text=True, encoding="utf-8",
                            errors="replace", timeout=timeout)
    return ((result.stdout or "") + (result.stderr or "")).strip()


def main(argv: list[str]) -> int:
    video = argv[0] if argv else str(REPO / ".tmp" / "userpic" / "scene.mp4")
    gui = REPO / "tools" / "board" / "video_gui.ps1"
    shot = REPO / ".tmp" / "gui_verdict.png"

    run_ps(r'''
$p = Get-Process powershell -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle -like '*视频播放*' } | Select-Object -First 1
if ($p) { $p.CloseMainWindow() | Out-Null; Write-Output 'closed leftover' } else { Write-Output 'nothing to close' }
''')

    print(f"launching with {video}")
    subprocess.Popen(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                      "-File", str(gui), "-Video", video])
    time.sleep(7)

    print("clicking 开始播放:", run_ps(CLICK_PS).splitlines()[0] if True else "")

    # The analysis runs first (a couple of seconds for 24 frames), then the upload, then playback.
    time.sleep(12)
    result = run_ps(SHOT_PS.replace("SHOT_PATH", f"'{shot}'"))
    print("screenshot:", result.splitlines()[0] if result else "(nothing)")
    print(f"file exists: {shot.exists()}  size: {shot.stat().st_size if shot.exists() else 0}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
