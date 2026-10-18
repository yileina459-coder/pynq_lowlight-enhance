@echo off
rem ---------------------------------------------------------------------------
rem Build the HDMI streaming overlay: PYNQ-Z2 base overlay + Sobel in the
rem pixel_pack -> pixel_unpack path.
rem
rem   build\overlay_hdmi\build.bat
rem
rem Steps
rem   1. fetch PYNQ v3.1.2 board sources (pinned tag, sparse clone)
rem   2. patch base.tcl for Vivado 2026.1 (version guard, IP repo path, PFM_NAME)
rem   3. unpack the HLS Sobel IP export into a local IP repository
rem   4. rebuild PYNQ's five HLS video IPs with this Vitis HLS
rem   5. create the base overlay block design
rem   6. rewire hdmi_in -> sobel_0 -> hdmi_out and drop the VDMA loopback
rem   7. implement and write the bitstream, then export .bit/.hwh for PYNQ
rem
rem Runtime: roughly 25-40 minutes (implementation dominates).
rem ---------------------------------------------------------------------------
setlocal enabledelayedexpansion

set HERE=%~dp0
set HERE=%HERE:~0,-1%
set REPO=%HERE%\..\..
set WORK=%HERE%\.work
set BASE=%WORK%\tree\boards\Pynq-Z2\base
set IPDIR=%WORK%\tree\boards\ip
set OUT=%REPO%\board\hdmi_stream

set HLS_EXPORT=%REPO%\build\hls\sobel\export\sobel.zip

if not exist "%HLS_EXPORT%" (
  echo ERROR: HLS IP export missing: %HLS_EXPORT%
  echo        Run tools\env\vitis_hls.bat -f build\hls\sobel\run_hls.tcl first.
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

echo === [3/7] unpack Sobel IP ===
if exist "%WORK%\sobel_ip" rmdir /s /q "%WORK%\sobel_ip"
mkdir "%WORK%\sobel_ip"
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "Expand-Archive -LiteralPath '%HLS_EXPORT%' -DestinationPath '%WORK%\sobel_ip' -Force"
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

echo === [6/7] insert Sobel and rewire ===
call "%REPO%\tools\env\vivado.bat" -mode batch -nojournal -nolog ^
     -source "%HERE%\insert_sobel.tcl" -tclargs "%BASE%" "%WORK%\sobel_ip"
if errorlevel 1 (
  echo ERROR: insert_sobel.tcl failed
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
if not exist "%OUT%\sobel_hdmi.bit" (
  echo ERROR: %OUT%\sobel_hdmi.bit was not produced
  exit /b 1
)

echo.
echo Done.
echo   bitstream : %OUT%\sobel_hdmi.bit
echo   handoff   : %OUT%\sobel_hdmi.hwh
echo   project   : %BASE%\base
exit /b 0
