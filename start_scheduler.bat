@echo off
cd /d "%~dp0"
:loop
echo [%date% %time%] Starting Scheduler...
python main.py scheduler
echo [%date% %time%] Scheduler exited. Restarting in 10s...
timeout /t 10 /nobreak >nul
goto loop
