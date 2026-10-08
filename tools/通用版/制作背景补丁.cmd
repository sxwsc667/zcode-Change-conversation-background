@echo off
chcp 65001 >nul
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0制作背景补丁.ps1" %*
set "result=%errorlevel%"
pause
exit /b %result%
