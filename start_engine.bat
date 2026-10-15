@echo off
REM start_engine.bat <engine-name>  - start ONE engine (heartbeat to the NEXXUS server)
if "%~1"=="" (echo usage: start_engine.bat axis-core & exit /b 1)
for %%I in ("%~dp0.") do set "ROOT=%%~fI"
set "ENG=%ROOT%\axis-ui-interface\project-X\silo_vault\%~1"
if not exist "%ENG%\mesh.py" (echo No mesh.py in %ENG% & exit /b 1)
call "%ROOT%\nexxus_env.bat"
cd /d "%ENG%"
python mesh.py
