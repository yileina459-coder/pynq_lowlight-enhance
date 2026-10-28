@echo off
rem ---------------------------------------------------------------------------
rem  Play a video on the board's HDMI output, with the preset chosen automatically.
rem
rem  Double-click  : opens a small window: pick the video, choose how the preset
rem                  is chosen, press Start.
rem  Drag and drop : drop a video onto this icon and it plays immediately with the
rem                  recommended setting (one preset for the whole clip).
rem
rem  The window itself lives in tools\board\upload_panel.ps1 so the text inside it can
rem  be proper Unicode; this launcher stays ASCII on purpose, because cmd.exe reads
rem  .bat files in the OEM code page and mangles anything else.
rem
rem  What it does, in order: decode the video on this PC, score every candidate
rem  preset on every frame, pick one (or a small schedule), copy the frames and the
rem  schedule to the board, and ask the resident demo to play them. Nothing is
rem  restarted, so the pixel stream stays up.
rem ---------------------------------------------------------------------------
setlocal
set "PS=powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\board\upload_panel.ps1""

if "%~1"=="" (
    start "" %PS%
    exit /b 0
)

start "" %PS% -File "%~1"
exit /b 0
