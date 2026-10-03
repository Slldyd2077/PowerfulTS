@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0powerfults.ps1" start
if errorlevel 1 (echo Startup failed. See the error above. & pause & exit /b 1)
