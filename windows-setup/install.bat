@echo off
setlocal

set "DIR=%~dp0"
if "%DIR:~-1%"=="\" set "DIR=%DIR:~0,-1%"

set "SSH_BAT=%DIR%\open-ssh.bat"
set "PISSD_BAT=%DIR%\open-pissd.bat"

echo Registering pissh:// (terminal) URL protocol...
reg add "HKCU\Software\Classes\pissh" /ve /d "URL:Pi SSH Protocol" /f >nul
reg add "HKCU\Software\Classes\pissh" /v "URL Protocol" /d "" /f >nul
reg add "HKCU\Software\Classes\pissh\shell\open\command" /ve /d "\"%SSH_BAT%\"" /f >nul

echo Registering pissd:// (explorer) URL protocol...
reg add "HKCU\Software\Classes\pissd" /ve /d "URL:PiSSD Explorer Protocol" /f >nul
reg add "HKCU\Software\Classes\pissd" /v "URL Protocol" /d "" /f >nul
reg add "HKCU\Software\Classes\pissd\shell\open\command" /ve /d "\"%PISSD_BAT%\"" /f >nul

echo.
echo Done. Restart your browser, then the Pi SSH and PiSSD buttons in Pi Hub will work.
echo.
echo Pi SSH requires plink.exe on PATH. If you don't have it:
echo   1. Install PuTTY: https://www.putty.org/
echo   2. Make sure C:\Program Files\PuTTY is on your PATH.
echo.
pause
