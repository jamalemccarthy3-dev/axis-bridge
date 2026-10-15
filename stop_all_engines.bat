@echo off
REM stops every window started by start_all_engines.bat
taskkill /F /T /FI "WINDOWTITLE eq ENGINE *" >nul 2>&1
echo Engines stopped.
