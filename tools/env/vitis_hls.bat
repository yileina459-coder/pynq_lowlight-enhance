@echo off
rem ---------------------------------------------------------------------------
rem Vitis HLS launcher wrapper for the local AMD 2026.1 install.
rem
rem Why this exists
rem   The AMD 2026.1 Windows installer used on this machine ships
rem     <install>\Vitis\bin\unwrapped\win64.o\vitis_hls.exe
rem   but does NOT ship the stock `vitis_hls.bat` launcher, so `vitis_hls` is
rem   not on PATH and the raw .exe aborts with
rem     ERROR: The RDI_DATADIR environment variable is not set.
rem   This wrapper reproduces what the stock launcher does (set RDI_PROG, let
rem   loader.bat assemble RDI_*/XILINX_HLS) and additionally exports
rem   XILINX_VIVADO, which `export_design -format ip_catalog` requires.
rem
rem Usage
rem   tools\env\vitis_hls.bat -f build\hls\<op>\run_hls.tcl
rem   tools\env\vitis_hls.bat -version
rem
rem Override the install location with AMD_INSTALL if it moves, e.g.
rem   set AMD_INSTALL=D:\AMD_vivado_vitis
rem ---------------------------------------------------------------------------
setlocal

if "%AMD_INSTALL%"=="" set AMD_INSTALL=D:\AMD_vivado_vitis
if "%AMD_VERSION%"=="" set AMD_VERSION=2026.1
set _AMD_ROOT=%AMD_INSTALL%\%AMD_VERSION%

if not exist "%_AMD_ROOT%\Vitis\bin\loader.bat" (
  echo ERROR: Vitis not found under "%_AMD_ROOT%".
  echo        Set AMD_INSTALL / AMD_VERSION to match your install.
  exit /b 1
)

set RDI_PROG=vitis_hls
set _RDI_CWD=%cd%
pushd "%_AMD_ROOT%\Vitis\bin"
set _RDI_BINROOT=%cd%
cd /d "%_RDI_CWD%"

rem Vivado environment first: export_design needs XILINX_VIVADO.
call "%_AMD_ROOT%\Vivado\.settings64-Vivado.bat"

rem Then the Vitis/HLS environment through the HLS tool's own launcher path.
call "%_RDI_BINROOT%\setupEnv.bat"
set RDI_SETUP_ENV_FUNCTION=DIRNAME
call "%_RDI_BINROOT%\setupEnv.bat" "%_RDI_BINROOT%" XILINX_HLS
call "%_RDI_BINROOT%\loader.bat" -exec %RDI_PROG% %*

popd
exit /b %errorlevel%
