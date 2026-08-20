@echo off
chcp 65001 >nul
cd /d "%~dp0"
title GROK REGISTER TOOL — All In One

set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
set PYTHONUNBUFFERED=1

if not exist venv (
    echo [*] Đang khởi tạo môi trường Python virtualenv...
    python -m venv venv 2>nul
    if errorlevel 1 (
        py -3.11 -m venv venv 2>nul || py -3 -m venv venv 2>nul
    )
)

if exist venv\Scripts\python.exe (
    set "PY=venv\Scripts\python.exe"
) else (
    set "PY=python"
)

if not exist config.json (
    if exist config.example.json (
        copy config.example.json config.json >nul
        echo [*] Đã tạo config.json từ mẫu.
    )
)

if not exist data\hotmails.txt (
    if not exist data mkdir data
    type nul > data\hotmails.txt
)

%PY% -u ui_menu.py
if errorlevel 1 (
    echo.
    echo [!] Nếu thiếu thư viện, hãy cài đặt bằng lệnh:
    echo     venv\Scripts\pip install -r requirements.txt
    echo.
    pause
)
