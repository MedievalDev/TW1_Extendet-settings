@echo off
REM Build for the TW Trainer (Two Worlds 1, version 1.7, 32-bit) with Tiny C Compiler.
REM Full build (all cheats). Add -DNUR_SPRINT=1 for the sprint-only variant.
setlocal
if defined TCC if not exist "%TCC%" set "TCC="
if not defined TCC if exist "%~dp0..\tcc\tcc.exe" set "TCC=%~dp0..\tcc\tcc.exe"
if not defined TCC if exist "%~dp0..\..\tcc\tcc.exe" set "TCC=%~dp0..\..\tcc\tcc.exe"
if not defined TCC if exist "%~dp0tcc.exe" set "TCC=%~dp0tcc.exe"
if not defined TCC (
	echo ERROR: tcc.exe not found. set TCC=C:\path\to\tcc.exe
	exit /b 1
)
"%TCC%" -v 2>&1 | findstr /i "i386" >nul || (echo ERROR: %TCC% is not a 32-bit tcc & exit /b 1)
if not exist "%~dp0bin\TWSEPlugins" mkdir "%~dp0bin\TWSEPlugins"
"%TCC%" -DNUR_SPRINT=0 -I"%~dp0..\twse" -I"%~dp0..\..\twse" -shared -o "%~dp0bin\TWSEPlugins\TWTrainer.dll" "%~dp0tw_trainer.c" || (echo Failed... & exit /b 1)
del "%~dp0bin\TWSEPlugins\TWTrainer.def" 2>nul
echo Compile success: bin\TWSEPlugins\TWTrainer.dll
exit /b 0
