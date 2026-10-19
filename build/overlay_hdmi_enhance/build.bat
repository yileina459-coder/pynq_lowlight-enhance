@echo off
rem ---------------------------------------------------------------------------
rem Build the HDMI overlay with the enhance kernel (low-latency vision terminal).
rem
rem   build\overlay_hdmi_enhance\build.bat
rem
rem Same seven steps as build\overlay_hdmi\build.bat, with two changes:
rem   * the kernel inserted between pixel_pack and pixel_unpack is enhance_stream
rem     instead of sobel_stream;
rem   * two axi_gpio cells and two hand-written RTL cells are added: one GPIO pair
rem     drives the 59 configuration bits (runtime presets), the other pair reads
rem     back the in-flight pixel count and its peak (measured latency).
rem
rem Output: board\hdmi_stream_enhance\enhance_hdmi.bit / .hwh
rem Runtime: roughly 30-45 minutes (implementation dominates).
rem ---------------------------------------------------------------------------
setlocal enabledelayedexpansion

set HERE=%~dp0
set HERE=%HERE:~0,-1%
set REPO=%HERE%\..\..
set WORK=%HERE%\.work
set BASE=%WORK%\tree\boards\Pynq-Z2\base
set IPDIR=%WORK%\tree\boards\ip
set OUT=%REPO%\board\hdmi_stream_enhance
set RTL=%REPO%\src\rtl

set HLS_EXPORT=%REPO%\build\hls\enhance\export\enhance.zip

if not exist "%HLS_EXPORT%" (
  echo ERROR: HLS IP export missing: %HLS_EXPORT%
  echo        Run tools\env\vitis_hls.bat -f build\hls\enhance\run_hls.tcl first.
  exit /b 1
)

echo === [1/7] fetch PYNQ sources ===
powershell -NoProfile -ExecutionPolicy Bypass -File "%HERE%\fetch_pynq.ps1" -Dest "%WORK%"
if errorlevel 1 (
  echo ERROR: fetch failed
  exit /b 1
)

echo === [2/7] patch base.tcl ===
python "%HERE%\patch_base_tcl.py" "%BASE%\base.tcl" "%IPDIR%"
if errorlevel 1 (
  echo ERROR: patch failed
  exit /b 1
)

echo === [3/7] unpack enhance IP ===
if exist "%WORK%\enhance_ip" rmdir /s /q "%WORK%\enhance_ip"
mkdir "%WORK%\enhance_ip"
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "Expand-Archive -LiteralPath '%HLS_EXPORT%' -DestinationPath '%WORK%\enhance_ip' -Force"
if errorlevel 1 (
  echo ERROR: failed to unpack %HLS_EXPORT%
  exit /b 1
)

rem vitis_hls has to be on PATH because PYNQ's build_ip.tcl shells out to it.
set PATH=%REPO%\tools\env;%PATH%

pushd "%BASE%"

echo === [4/7] build PYNQ HLS video IPs ===
call "%REPO%\tools\env\vivado.bat" -mode batch -nojournal -nolog -source build_ip.tcl
if errorlevel 1 (
  echo ERROR: PYNQ HLS IP build failed
  popd
  exit /b 1
)

echo === [5/7] base overlay block design ===
if exist "%BASE%\base" rmdir /s /q "%BASE%\base"
call "%REPO%\tools\env\vivado.bat" -mode batch -nojournal -nolog -source base.tcl
if errorlevel 1 (
  echo ERROR: base.tcl failed
  popd
  exit /b 1
)

echo === [6/7] insert enhance, config GPIO, latency monitor ===
call "%REPO%\tools\env\vivado.bat" -mode batch -nojournal -nolog ^
     -source "%HERE%\insert_enhance.tcl" -tclargs "%BASE%" "%WORK%\enhance_ip" "%RTL%"
if errorlevel 1 (
  echo ERROR: insert_enhance.tcl failed
  popd
  exit /b 1
)

echo === [7/7] implement and export ===
call "%REPO%\tools\env\vivado.bat" -mode batch -nojournal -nolog -source "%HERE%\build_bitstream.tcl"
if errorlevel 1 (
  echo ERROR: bitstream build failed
  popd
  exit /b 1
)

popd

if not exist "%OUT%" mkdir "%OUT%"
if not exist "%OUT%\enhance_hdmi.bit" (
  echo ERROR: %OUT%\enhance_hdmi.bit was not produced
  exit /b 1
)

echo.
echo Done.
echo   bitstream : %OUT%\enhance_hdmi.bit
echo   handoff   : %OUT%\enhance_hdmi.hwh
echo   project   : %BASE%\base
exit /b 0
