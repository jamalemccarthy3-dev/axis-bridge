@echo off
REM Starts the module gateway (http://127.0.0.1:8080). Modules are reached by hostname:
REM   http://blog.localhost:8080/      http://picthis.localhost:8080/
cd /d "%~dp0"
python gateway.py --check || (echo Fix ports.json first. & pause & exit /b 1)
python -u gateway.py
