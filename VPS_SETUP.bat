@echo off
setlocal EnableExtensions
chcp 65001 >nul
title GrokReg VPS Setup
set "ROOT=%~dp0"
set "TOOL=%ROOT%grok_tool"
echo === GrokReg VPS setup ===
where python >nul 2>&1 || (echo [LOI] Chua cai Python 3.12. Cai tu python.org va chon Add to PATH.& pause & exit /b 1)
if not exist "%TOOL%\venv\Scripts\python.exe" (
  echo [..] Tao Python venv...
  python -m venv "%TOOL%\venv" || (echo [LOI] Tao venv that bai.& pause & exit /b 1)
)
echo [..] Cai dependencies...
"%TOOL%\venv\Scripts\python.exe" -m pip install --upgrade pip
"%TOOL%\venv\Scripts\pip.exe" install -r "%TOOL%\requirements.txt" || (echo [LOI] Cai requirements that bai.& pause & exit /b 1)
echo [..] Cai Camoufox solver...
"%TOOL%\venv\Scripts\pip.exe" install "camoufox[geoip]" quart patchright rich || (echo [LOI] Cai Camoufox that bai.& pause & exit /b 1)
"%TOOL%\venv\Scripts\python.exe" -m camoufox fetch || (echo [LOI] Tai browser Camoufox that bai.& pause & exit /b 1)
echo.
echo SETUP XONG. Tiep theo copy config.json, gsheets_service_account.json va data tu may cu.
pause
exit /b 0
