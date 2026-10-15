@echo off
REM ============================================================
REM  start_domain_hubs.bat  -  start the four domain hubs, each as its own local server on its own port.
REM  Placeholders (change them here, or in nexxus_env.bat, before running):
REM     NEXXUS_PORT_SPORTS=8721   NEXXUS_PORT_MARKETS=8722   NEXXUS_PORT_LOGISTICS=8723   NEXXUS_PORT_ECONOMICS=8724
REM  Every hub listens on 127.0.0.1 only. The NEXXUS home screen sends domain questions to these ports (domain_dispatch.py).
REM ============================================================
cd /d "%~dp0" || (echo Folder not found & pause & exit /b 1)
if exist "%~dp0nexxus_env.bat" call "%~dp0nexxus_env.bat"
if not defined NEXXUS_PORT_SPORTS    set NEXXUS_PORT_SPORTS=8721
if not defined NEXXUS_PORT_MARKETS   set NEXXUS_PORT_MARKETS=8722
if not defined NEXXUS_PORT_LOGISTICS set NEXXUS_PORT_LOGISTICS=8723
if not defined NEXXUS_PORT_ECONOMICS set NEXXUS_PORT_ECONOMICS=8724
echo Starting the domain hubs on 127.0.0.1: sports %NEXXUS_PORT_SPORTS%, markets %NEXXUS_PORT_MARKETS%, logistics %NEXXUS_PORT_LOGISTICS%, economics %NEXXUS_PORT_ECONOMICS%
for %%D in (sports markets logistics economics) do start "NEXXUS hub %%D" /min python domain_hub_server.py %%D
echo Done. Check them with:  curl http://127.0.0.1:%NEXXUS_PORT_SPORTS%/health
