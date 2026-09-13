@echo off
REM Baut tw1_Extendet-settings.exe (eine Datei, ohne Konsole) mit PyInstaller.
REM Die Plugin-DLL aus bin\TWSEPlugins wird eingebettet, damit die Exe sie
REM selbst ins Spiel kopieren kann. Vorher build_extended.bat ausfuehren.
setlocal
set PY=C:\Users\marco\AppData\Local\Programs\Python\Python313\python.exe
cd /d "%~dp0"
if not exist "bin\TWSEPlugins\TWExtended.dll" (echo FEHLER: erst build_extended.bat & exit /b 1)
"%PY%" -m PyInstaller --noconfirm --clean --onefile --windowed --name "tw1_Extendet-settings" ^
  --icon tw1_extended.ico --add-data "tw1_extended.ico;." ^
  --add-data "bin\TWSEPlugins\TWExtended.dll;." --hidden-import theme ^
  tw1_extended_settings.py || (echo Failed... & exit /b 1)
echo Fertig: dist\tw1_Extendet-settings.exe
exit /b 0
