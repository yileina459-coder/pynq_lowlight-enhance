@echo off
rem Sweep the horizontal compensation so the picture lines up. Watch the screen and press Ctrl+C
rem when it looks right, then note the number and fix it with set_roll.ps1 -Value <number>.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\board\set_roll.ps1" -Sweep
pause
