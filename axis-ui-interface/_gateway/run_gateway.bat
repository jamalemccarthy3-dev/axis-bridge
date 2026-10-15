@echo off
REM The module gateway. It starts the modules marked keep_running (hidden), restarts them if they crash,
REM and restarts itself if it ever stops. Output goes to logs\gateway.log.
cd /d "%~dp0"
if not exist logs mkdir logs
:loop
python -u gateway.py >> logs\gateway.log 2>&1
timeout /t 5 /nobreak >nul
goto loop
