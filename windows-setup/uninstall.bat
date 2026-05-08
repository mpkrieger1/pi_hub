@echo off
echo Removing pissh:// and pissd:// URL protocols...
reg delete "HKCU\Software\Classes\pissh" /f >nul 2>&1
reg delete "HKCU\Software\Classes\pissd" /f >nul 2>&1
echo Done.
pause
