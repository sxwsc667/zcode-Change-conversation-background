@echo off
chcp 65001 >nul
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0安装对话背景.ps1" %*
set "result=%errorlevel%"
pause
exit /b %result%
