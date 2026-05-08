@echo off
REM Auto-login SSH to mpk-pi via plink. Invoked by the pissh:// URL protocol.

where /q plink.exe
if errorlevel 1 (
    echo plink.exe not found on PATH.
    echo Install PuTTY from https://www.putty.org/ and make sure plink.exe is on PATH.
    echo Default install: C:\Program Files\PuTTY
    pause
    exit /b 1
)

start "Pi SSH" cmd /k plink.exe -ssh mpkrieger1@mpk-pi -pw "M@tt1436" -t
exit
