@echo off
del "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\AxisGateway.vbs" 2>nul
echo Gateway autostart removed. Stop it in Task Manager (python.exe) or at next logoff.
pause
