@echo off
setlocal EnableExtensions
chcp 65001 >nul
title GrokReg VPS Setup
set "ROOT=%~dp0"
set "TOOL=%ROOT%grok_tool"
echo === GrokReg VPS setup ===
set "PYTHON=C:\Program Files\Python312\python.exe"
if not exist "%PYTHON%" (
  echo [..] Chua co Python 3.12, dang cai tu python.org...
  powershell -NoProfile -ExecutionPolicy Bypass -Command "$u='https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe';$f=Join-Path $env:TEMP 'python312-grokreg.exe';Invoke-WebRequest $u -OutFile $f;Start-Process $f -ArgumentList '/quiet','InstallAllUsers=1','PrependPath=1','Include_test=0' -Wait"
)
if not exist "%PYTHON%" set "PYTHON=python"
%PYTHON% --version >nul 2>&1 || (echo [LOI] Khong cai duoc Python. Kiem tra Internet/quyen Administrator.& pause & exit /b 1)
if not exist "%TOOL%\venv\Scripts\python.exe" (
  echo [..] Tao Python venv...
  "%PYTHON%" -m venv "%TOOL%\venv" || (echo [LOI] Tao venv that bai.& pause & exit /b 1)
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
