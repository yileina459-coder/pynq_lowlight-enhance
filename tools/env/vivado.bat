@echo off
rem ---------------------------------------------------------------------------
rem Vivado launcher with the project-local environment (2026.1).
rem
rem Vivado is on PATH in this install, but every reproducible build should call
rem the same entry point so that the settings file that a clean machine needs is
rem written down in one place. Override with AMD_INSTALL / AMD_VERSION.
rem ---------------------------------------------------------------------------
setlocal

if "%AMD_INSTALL%"=="" set AMD_INSTALL=D:\AMD_vivado_vitis
if "%AMD_VERSION%"=="" set AMD_VERSION=2026.1
set _AMD_ROOT=%AMD_INSTALL%\%AMD_VERSION%

if not exist "%_AMD_ROOT%\Vivado\bin\vivado.bat" (
  echo ERROR: Vivado not found under "%_AMD_ROOT%".
  echo        Set AMD_INSTALL / AMD_VERSION to match your install.
  exit /b 1
)

call "%_AMD_ROOT%\Vivado\settings64.bat"
vivado %*

exit /b %errorlevel%
