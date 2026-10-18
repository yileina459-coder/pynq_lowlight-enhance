@echo off
rem ---------------------------------------------------------------------------
rem Build the DMA verification overlay end to end.
rem
rem   build\overlay_dma\build.bat
rem
rem Steps
rem   1. unpack the HLS IP export (sobel.zip) into a local IP repository, because
rem      Vivado's ip_repo_paths wants a directory and has no unzip of its own
rem   2. run build.tcl (block design -> implementation -> bitstream -> XSA)
rem   3. split the XSA into sobel_dma.bit / sobel_dma.hwh and copy them to
rem      board\dma_sobel\ where the PYNQ notebook expects them
rem ---------------------------------------------------------------------------
setlocal enabledelayedexpansion

set HERE=%~dp0
set HERE=%HERE:~0,-1%
set REPO=%HERE%\..\..

set HLS_EXPORT=%REPO%\build\hls\sobel\export\sobel.zip
set IPREPO=%HERE%\iprepo
set OUTDIR=%HERE%\out
set BOARD_DIR=%REPO%\board\dma_sobel

if not exist "%HLS_EXPORT%" (
  echo ERROR: HLS IP export not found: %HLS_EXPORT%
  echo        Run tools\env\vitis_hls.bat -f build\hls\sobel\run_hls.tcl first.
  exit /b 1
)

echo === [1/3] unpack HLS IP ===
if exist "%IPREPO%" rmdir /s /q "%IPREPO%"
mkdir "%IPREPO%"
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "Expand-Archive -LiteralPath '%HLS_EXPORT%' -DestinationPath '%IPREPO%' -Force"
if errorlevel 1 (
  echo ERROR: failed to unpack %HLS_EXPORT%
  exit /b 1
)
dir /b "%IPREPO%"

echo === [2/3] Vivado build ===
call "%REPO%\tools\env\vivado.bat" -mode batch -nojournal -nolog -source "%HERE%\build.tcl"
if errorlevel 1 (
  echo ERROR: Vivado build failed
  exit /b 1
)

echo === [3/3] split XSA into bit + hwh ===
if not exist "%OUTDIR%\design_1.xsa" (
  echo ERROR: XSA not produced
  exit /b 1
)

set STAGE=%OUTDIR%\xsa_stage
if exist "%STAGE%" rmdir /s /q "%STAGE%"
mkdir "%STAGE%"
rem Expand-Archive refuses non-.zip extensions, and the XSA is just a zip
rem archive, so use the .NET API instead of the cmdlet.
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "Add-Type -AssemblyName System.IO.Compression.FileSystem; [System.IO.Compression.ZipFile]::ExtractToDirectory('%OUTDIR%\design_1.xsa', '%STAGE%')"
if errorlevel 1 (
  echo ERROR: failed to unpack the XSA
  exit /b 1
)

if not exist "%BOARD_DIR%" mkdir "%BOARD_DIR%"

rem The .bit inside the XSA may carry either the wrapper or the block design
rem name depending on the Vivado version, so take whichever is there. PYNQ needs
rem the .bit and .hwh to share one base name, which is what the copy enforces.
set BITSRC=
for %%f in ("%STAGE%\*.bit") do set BITSRC=%%f
if "%BITSRC%"=="" (
  echo ERROR: no .bit inside the XSA
  dir /b "%STAGE%"
  exit /b 1
)
copy /y "%BITSRC%" "%BOARD_DIR%\sobel_dma.bit" >nul
copy /y "%STAGE%\design_1.hwh" "%BOARD_DIR%\sobel_dma.hwh" >nul
if errorlevel 1 (
  echo ERROR: expected design_1_wrapper.bit and design_1.hwh inside the XSA
  dir /b /s "%STAGE%"
  exit /b 1
)

echo.
echo Done.
echo   bitstream : %BOARD_DIR%\sobel_dma.bit
echo   handoff   : %BOARD_DIR%\sobel_dma.hwh
echo   reports   : %OUTDIR%\util_impl.rpt, timing_impl.rpt
exit /b 0
