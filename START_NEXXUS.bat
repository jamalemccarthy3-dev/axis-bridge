@echo off
REM ============================================================
REM  START_NEXXUS.bat  -  one double-click: starts the NEXXUS server and all engines
REM  (only what is not already running) and the watchdog that restarts them if they stop.
REM  Safe to run any time: it never starts a duplicate and never kills anything.
REM  Progress is written to logs\autostart.log
REM ============================================================
cd /d "%~dp0"
if not exist "%~dp0nexxus_env.bat" python "%~dp0setup_nexxus.py"
echo Starting NEXXUS (server, engines, watchdog)...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0nexxus_autostart.ps1" -NoDelay
echo.
echo Done. Open http://localhost:8000/  (log: logs\autostart.log)
timeout /t 8 >nul
