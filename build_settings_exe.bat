@echo off
REM Baut tw1_Extendet-settings.exe (eine Datei, ohne Konsole) mit PyInstaller.
REM Eingebettet: Plugin-DLL aus bin\TWSEPlugins, twse.dll aus bin (TWSE von
REM buglord, CC0) und untested.json fuer das Testfenster. Vorher
REM build_extended.bat ausfuehren.
setlocal
set PY=C:\Users\marco\AppData\Local\Programs\Python\Python313\python.exe
cd /d "%~dp0"
if not exist "bin\TWSEPlugins\TWExtended.dll" (echo FEHLER: erst build_extended.bat & exit /b 1)
if not exist "bin\twse.dll" (echo FEHLER: bin\twse.dll fehlt & exit /b 1)
"%PY%" -m PyInstaller --noconfirm --clean --onefile --windowed --name "tw1_Extendet-settings" ^
  --icon tw1_extended.ico --add-data "tw1_extended.ico;." ^
  --add-data "bin\TWSEPlugins\TWExtended.dll;." --add-data "bin\twse.dll;." ^
  --add-data "untested.json;." ^
  --hidden-import theme --hidden-import twse_patch ^
  --hidden-import foxfeedback --hidden-import foxfeedback_ui ^
  tw1_extended_settings.py || (echo Failed... & exit /b 1)
echo Fertig: dist\tw1_Extendet-settings.exe
exit /b 0
