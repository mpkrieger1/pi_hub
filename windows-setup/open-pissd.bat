@echo off
REM Open Windows Explorer at the PiSSD network share. Invoked by the pissd:// URL protocol.
start "" explorer.exe \\mpk-pi\PiSSD
exit
