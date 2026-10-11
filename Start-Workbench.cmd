@echo off
powershell.exe -NoProfile -File "%~dp0Start-Workbench.ps1"
if errorlevel 1 pause
