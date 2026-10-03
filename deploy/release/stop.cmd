@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0powerfults.ps1" stop
if errorlevel 1 (echo Stop failed. See the error above. & pause & exit /b 1)
