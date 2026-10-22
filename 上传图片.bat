@echo off
rem ---------------------------------------------------------------------------
rem  Show a picture on the board's HDMI output without touching a command line.
rem
rem  Double-click  : opens a small window where you pick the file.
rem  Drag and drop : drop one or more pictures onto this icon and they upload
rem                  immediately, using the default "keep aspect ratio" fit.
rem
rem  The window itself lives in tools\board\upload_gui.ps1 so the text is proper
rem  Unicode; this launcher stays ASCII on purpose, because cmd.exe reads .bat
rem  files in the OEM code page and mangles anything else.
rem ---------------------------------------------------------------------------
setlocal
set "PS=powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\board\upload_gui.ps1""

if "%~1"=="" (
    start "" %PS%
    exit /b 0
)

rem One or more files were dropped: upload each in turn, last one wins.
for %%F in (%*) do (
    start /wait "" %PS% -Image "%%~fF"
)
exit /b 0