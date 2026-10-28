@echo off
rem ---------------------------------------------------------------------------
rem  Upload a picture OR a video to the board - one window for both.
rem
rem  Double-click  : opens the window; pick any file (jpg/png/bmp/gif/webp for
rem                  pictures, mp4/mov/mkv/avi/gif/webp for videos) and it works
rem                  out which kind it is, then shows only the options that apply.
rem  Drag and drop : drop a file onto this icon and the window opens with it
rem                  already selected.
rem
rem  Pictures are converted, uploaded and displayed; videos are decoded,
rem  analysed for the best preset, uploaded and played through the FPGA. Nothing
rem  restarts the demo process, so the pixel stream stays up.
rem
rem  The window lives in tools\board\upload_panel.ps1 so its text can be proper
rem  Unicode; this launcher stays ASCII because cmd.exe reads .bat files in the
rem  OEM code page and mangles anything else.
rem ---------------------------------------------------------------------------
setlocal
set "PS=powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\board\upload_panel.ps1""

if "%~1"=="" (
    start "" %PS%
    exit /b 0
)

start "" %PS% -File "%~1"
exit /b 0
