@echo off
rem Measure the output's horizontal phase from the OBS preview, write the compensation, verify it.
rem Run it after the demo starts (the phase is redrawn whenever the pixel stream starts).
if not exist "%~dp0tools\board\fix_offset.ps1" (
    echo.
    echo This launcher has to sit in the repository root - it needs the tools\board folder next to it.
    echo Put it back where it was, or make a Desktop shortcut to it instead of moving the file.
    echo.
    pause
    exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\board\fix_offset.ps1"
pause
