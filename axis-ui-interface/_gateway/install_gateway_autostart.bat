@echo off
REM Makes the gateway (and through it every keep_running module) start hidden at every Windows login.
cd /d "%~dp0"
> "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\AxisGateway.vbs" echo CreateObject("WScript.Shell").Run "wscript //nologo ""%~dp0hidden_start_gateway.vbs""", 0, False
echo Gateway autostart installed.
pause
