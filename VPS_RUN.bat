@echo off
setlocal EnableExtensions
chcp 65001 >nul
title GrokReg VPS 24/7
set "ROOT=%~dp0"
set "TOOL=%ROOT%grok_tool"
if not exist "%TOOL%\venv\Scripts\python.exe" (
  echo [LOI] Chua setup. Chay VPS_SETUP.bat truoc.
  pause
  exit /b 1
)
cd /d "%TOOL%"
echo [..] Cai autostart dashboard 24/7...
powershell -NoProfile -ExecutionPolicy Bypass -File "%TOOL%\CAI_SERVER_NEN.ps1"
echo.
echo Dashboard: http://127.0.0.1:8787/
echo Kiem tra:  %TOOL%\venv\Scripts\python.exe -m web_console.daemon --status
echo.
start "" "http://127.0.0.1:8787/"
pause
exit /b 0
