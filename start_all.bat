@echo off
cd /d "%~dp0"
echo [%date% %time%] Starting UI and Auto Scheduler...
start "MetaForge UI" cmd /k "python ui/app.py"
