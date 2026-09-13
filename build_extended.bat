@echo off
REM Build fuer TWExtended (Two Worlds 1, Version 1.7, 32-bit) mit Tiny C Compiler.
setlocal
if defined TCC if not exist "%TCC%" set "TCC="
if not defined TCC if exist "%~dp0..\tcc\tcc.exe" set "TCC=%~dp0..\tcc\tcc.exe"
if not defined TCC if exist "%~dp0tcc.exe" set "TCC=%~dp0tcc.exe"
if not defined TCC (
	echo FEHLER: tcc.exe nicht gefunden. set TCC=C:\Pfad\zu\tcc.exe
	exit /b 1
)
"%TCC%" -v 2>&1 | findstr /i "i386" >nul || (echo FEHLER: %TCC% ist kein 32-bit tcc & exit /b 1)
if not exist "%~dp0bin\TWSEPlugins" mkdir "%~dp0bin\TWSEPlugins"
"%TCC%" -I"%~dp0twse" -I"%~dp0..\twse" -shared -o "%~dp0bin\TWSEPlugins\TWExtended.dll" "%~dp0tw_extended.c" || (echo Failed... & exit /b 1)
del "%~dp0bin\TWSEPlugins\TWExtended.def" 2>nul
echo Compile success: bin\TWSEPlugins\TWExtended.dll
exit /b 0
