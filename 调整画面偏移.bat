@echo off
rem Measure the output's horizontal phase from the OBS preview, write the compensation, verify it.
rem Run it after the demo starts (the phase is redrawn whenever the pixel stream starts).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\board\fix_offset.ps1"
pause
